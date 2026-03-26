#!/usr/bin/env python3
"""Run benchmark modes on a normalized manifest."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.dataset import load_benchmark_manifest
from src.benchmark.modes.gpt52_single_pass import run_gpt52_single_pass_case
from src.benchmark.modes.pipeline import run_pipeline_benchmark_case
from src.benchmark.reporting import write_summary_outputs


MODE_RUNNERS = {
    "solvita_pipeline": run_pipeline_benchmark_case,
    "gpt52_single_pass": run_gpt52_single_pass_case,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run benchmark modes on a frozen manifest.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["solvita_pipeline", "gpt52_single_pass"],
        choices=sorted(MODE_RUNNERS.keys()),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--config-path", type=str, default="config/models.yaml")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Number of problems to run in parallel. Uses separate worker processes.",
    )
    return parser.parse_args()


def load_problem_payload(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_problem_modes(
    item: Any,
    modes: List[str],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    payload = load_problem_payload(item.problem_payload_path)
    rows: List[Dict[str, Any]] = []

    for mode in modes:
        runner = MODE_RUNNERS[mode]
        try:
            result = runner(problem_payload=payload, config=config)
            row = {
                "problem_id": result.problem_id,
                "mode": result.mode,
                "status": result.status,
                "compile_success": result.compile_success,
                "passed_tests": result.passed_tests,
                "total_tests": result.total_tests,
                "pass_rate": result.pass_rate,
                "elapsed_total_s": result.elapsed_total_s,
                "llm_infer_s": result.llm_infer_s,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "token_usage_source": result.token_usage_source,
                "error": result.error,
                "hack_result": result.hack_result,
                "hack_passed": result.hack_passed,
                "generator_failure_kind": result.generator_failure_kind,
                "generator_failure_reason": result.generator_failure_reason,
                "workflow_log_path": result.workflow_log_path,
            }
        except Exception as exc:
            row = {
                "problem_id": item.problem_id,
                "mode": mode,
                "status": "error",
                "compile_success": False,
                "passed_tests": 0,
                "total_tests": 0,
                "pass_rate": 0.0,
                "elapsed_total_s": 0.0,
                "llm_infer_s": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "token_usage_source": None,
                "error": str(exc),
                "hack_result": None,
                "hack_passed": None,
                "generator_failure_kind": None,
                "generator_failure_reason": None,
                "workflow_log_path": None,
            }
        rows.append(row)

    return rows


def main() -> None:
    args = parse_args()
    items = load_benchmark_manifest(args.manifest)
    if args.limit is not None:
        items = items[: args.limit]

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.jsonl"

    config = {
        "config_path": args.config_path,
        "benchmark_output_dir": str(output_dir),
    }
    rows: List[Dict[str, Any]] = []
    max_workers = max(1, int(args.max_workers))

    with results_path.open("w", encoding="utf-8") as fh:
        if max_workers == 1 or len(items) <= 1:
            for item in items:
                for row in _run_problem_modes(item, args.modes, config):
                    rows.append(row)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
        else:
            worker_count = min(max_workers, len(items), os.cpu_count() or max_workers)
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                future_to_problem = {
                    executor.submit(_run_problem_modes, item, args.modes, config): item.problem_id
                    for item in items
                }
                for future in as_completed(future_to_problem):
                    for row in future.result():
                        rows.append(row)
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                        fh.flush()

    write_summary_outputs(output_dir, rows)


if __name__ == "__main__":
    main()
