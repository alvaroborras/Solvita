"""Solvita Agent Entry Point - LangGraph Implementation"""

import argparse
import json
from pathlib import Path
from loguru import logger
from src.graph import run_workflow


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Solvita - Algorithm Problem Solving Agent")
    parser.add_argument("--input", type=str, required=True, help="Input problem file (JSON)")
    parser.add_argument("--output", type=str, default="solution.cpp", help="Output solution file")
    parser.add_argument("--model", type=str, default="gpt-4", help="LLM model to use")
    parser.add_argument("--temperature", type=float, default=0.1, help="LLM temperature")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max refinement iterations")
    parser.add_argument("--config", type=str, default="config", help="Config directory path")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
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


def main():
    """Main entry point - runs LangGraph workflow"""
    args = parse_args()

    # Configure logger
    if args.verbose:
        logger.remove()
        logger.add(lambda msg: print(msg, end=""), level="DEBUG")

    logger.info("=" * 60)
    logger.info("Solvita Agent - LangGraph Implementation")
    logger.info("=" * 60)

    # Load problem
    try:
        problem_input = load_problem(args.input)
    except Exception as e:
        logger.error(f"Failed to load problem: {e}")
        return

    # Prepare configuration
    config = {
        "model": args.model,
        "temperature": args.temperature,
        "max_iterations": args.max_iterations,
        "config_path": args.config,
    }

    logger.info(f"Configuration: {config}")

    # Run workflow
    try:
        final_state = run_workflow(problem_input, config)

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Save solution
    save_solution(final_state, args.output)

    # Print summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Execution Summary:")
    logger.info(f"  Status: {final_state.get('status')}")
    logger.info(f"  Iterations: {final_state.get('iteration')}")
    logger.info(f"  LLM Calls: {final_state.get('llm_calls')}")
    tests = final_state.get('tests', {})
    logger.info(f"  Tests: {tests.get('passed_tests', 0)}/{tests.get('total_tests', 0)} passed")
    logger.info(f"  Pass Rate: {tests.get('pass_rate', 0.0):.1%}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

