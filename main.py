"""Solvita Agent Entry Point - LangGraph Implementation"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from loguru import logger
import src.events as events
from src.graph import run_workflow


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Solvita - Algorithm Problem Solving Agent")
    parser.add_argument("--input", type=str, help="Input problem file (JSON)")
    parser.add_argument(
        "--problem-description",
        type=str,
        default=None,
        help="Problem description text (alternative to --input, used by CLI interactive mode)",
    )
    parser.add_argument("--output", type=str, default="solution.cpp", help="Output solution file")
    parser.add_argument("--model", type=str, default=None,
                        help="LLM model to use (overrides config/models.yaml; if omitted, yaml/env decides)")
    parser.add_argument("--temperature", type=float, default=0.1, help="LLM temperature")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max refinement iterations")
    parser.add_argument("--config", type=str, default="config", help="Config directory path")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--stream-events",
        action="store_true",
        help=(
            "Emit structured NDJSON events to stdout (one JSON object per line). "
            "Loguru output is redirected to solvita_run.log. "
            "Used by the Solvita CLI frontend."
        ),
    )
    return parser.parse_args()


def load_problem(input_path: str) -> dict:
    """Load problem from JSON file"""
    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(f"Problem file not found: {input_path}")

    with open(path, "r", encoding="utf-8") as f:
        problem_data = json.load(f)

    logger.info(f"Loaded problem from {input_path}")
    return problem_data


def build_problem_from_description(description: str) -> dict:
    """Build a minimal problem dict from a plain-text description."""
    return {
        "description": description,
        "time_limit": 2000,
        "space_limit": 256,
        "public_tests": [],
    }


def save_solution(final_state: dict, output_path: str) -> None:
    """Save solution to file"""
    solution_code = final_state.get("solution", {}).get("code", "")

    if solution_code:
        output_file = Path(output_path)
        output_file.write_text(solution_code, encoding="utf-8")
        logger.info(f"✓ Solution saved to {output_path}")
    else:
        logger.warning("No solution generated")

    # Also save metadata
    metadata_path = Path(output_path).with_suffix(".metadata.json")
    tests = final_state.get("tests", {})
    metadata = {
        "status": final_state.get("status"),
        "iteration": final_state.get("iteration"),
        "llm_calls": final_state.get("llm_calls"),
        "pass_rate": tests.get("pass_rate", 0.0),
        "total_tests": tests.get("total_tests", 0),
        "passed_tests": tests.get("passed_tests", 0),
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"✓ Metadata saved to {metadata_path}")


def _setup_stream_logging() -> None:
    """Redirect loguru output to a log file so stdout stays clean for NDJSON."""
    logger.remove()
    # enqueue=False: synchronous file logging avoids fork-safety issues on Linux.
    # With enqueue=True a background thread holds internal locks; subprocess.run()
    # with preexec_fn forks the process and the child inherits locked mutexes,
    # causing the validator/compiler subprocesses to deadlock and time out.
    logger.add("solvita_run.log", level="DEBUG", enqueue=False, encoding="utf-8")


def main():
    """Main entry point - runs LangGraph workflow"""
    args = parse_args()

    # ----------------------------------------------------------------
    # Stream-events mode: configure event emitter, redirect logs
    # ----------------------------------------------------------------
    if args.stream_events:
        _setup_stream_logging()
        events.configure(enabled=True)
    elif args.verbose:
        logger.remove()
        logger.add(lambda msg: print(msg, end=""), level="DEBUG")

    logger.info("=" * 60)
    logger.info("Solvita Agent - LangGraph Implementation")
    logger.info("=" * 60)

    # ----------------------------------------------------------------
    # Resolve problem input
    # ----------------------------------------------------------------
    _tmp_file = None
    try:
        if args.input:
            problem_input = load_problem(args.input)
            input_path = args.input
        elif args.problem_description:
            problem_input = build_problem_from_description(args.problem_description)
            # Write to a temp file so downstream code that expects a path still works
            _tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(problem_input, _tmp)
            _tmp.close()
            _tmp_file = _tmp.name
            input_path = _tmp_file
            logger.info("Built problem from --problem-description")
        else:
            logger.error("Either --input or --problem-description is required")
            if args.stream_events:
                events.emit("error", message="Either --input or --problem-description is required")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load problem: {e}")
        if args.stream_events:
            events.emit("error", message=str(e))
        return

    # ----------------------------------------------------------------
    # Prepare configuration
    # ----------------------------------------------------------------
    config = {
        "temperature": args.temperature,
        "max_iterations": args.max_iterations,
        "config_path": args.config,
    }
    if args.model is not None:
        config["model"] = args.model
    logger.info(f"Configuration: {config}")

    # ----------------------------------------------------------------
    # Run workflow
    # ----------------------------------------------------------------
    try:
        if args.stream_events:
            from src.graph.workflow import stream_workflow
            final_state = stream_workflow(problem_input, config)
        else:
            final_state = run_workflow(problem_input, config)
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        if args.stream_events:
            events.emit("error", message=str(e))
        import traceback
        traceback.print_exc()
        return
    finally:
        if _tmp_file:
            try:
                Path(_tmp_file).unlink(missing_ok=True)
            except Exception:
                pass

    # ----------------------------------------------------------------
    # Save solution
    # ----------------------------------------------------------------
    save_solution(final_state, args.output)

    if args.stream_events:
        # Emit the solution file path so CLI knows where to display it
        events.emit("solution_saved", path=args.output)

    # ----------------------------------------------------------------
    # Print summary (only in non-stream mode)
    # ----------------------------------------------------------------
    if not args.stream_events:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Execution Summary:")
        logger.info(f"  Status: {final_state.get('status')}")
        logger.info(f"  Iterations: {final_state.get('iteration')}")
        logger.info(f"  LLM Calls: {final_state.get('llm_calls')}")
        tests = final_state.get("tests", {})
        logger.info(f"  Tests: {tests.get('passed_tests', 0)}/{tests.get('total_tests', 0)} passed")
        logger.info(f"  Pass Rate: {tests.get('pass_rate', 0.0):.1%}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
