"""Benchmark adapter for the current Solvita pipeline."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
import time
from typing import Any, Dict

from loguru import logger

from src.benchmark.evaluation import score_solution_on_official_tests
from src.benchmark.types import BenchmarkResult
from src.graph.workflow import run_workflow
from src.llm.token_usage import ensure_token_usage_accumulator, get_token_usage_snapshot


def build_pipeline_benchmark_config(config: Dict[str, Any] | None) -> Dict[str, Any]:
    benchmark_config = deepcopy(config or {})
    ensure_token_usage_accumulator(benchmark_config)
    return benchmark_config


def _sanitize_log_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)
    return cleaned.strip("._") or "unknown"


def _resolve_workflow_log_path(config: Dict[str, Any], problem_id: str, mode: str) -> Path | None:
    output_dir = config.get("benchmark_output_dir")
    if not output_dir:
        return None
    root = Path(output_dir)
    repeat_index = int(config.get("benchmark_repeat_index", 1) or 1)
    suffix = f".r{repeat_index}" if repeat_index > 1 else ""
    return root / "logs" / mode / f"{_sanitize_log_stem(problem_id)}{suffix}.log"


def run_pipeline_benchmark_case(
    problem_payload: Dict[str, Any],
    config: Dict[str, Any] | None = None,
) -> BenchmarkResult:
    problem_id = str(problem_payload.get("problem_id", "unknown"))
    raw_problem = problem_payload.get("raw_problem", {})
    official_tests = list(problem_payload.get("official_tests", []) or [])
    benchmark_config = build_pipeline_benchmark_config(config)
    workflow_log_path = _resolve_workflow_log_path(benchmark_config, problem_id, "solvita_pipeline")
    sink_id = None
    if workflow_log_path is not None:
        workflow_log_path.parent.mkdir(parents=True, exist_ok=True)
        sink_id = logger.add(str(workflow_log_path), enqueue=False, backtrace=True, diagnose=False)

    started_at = time.time()
    try:
        try:
            final_state = run_workflow(raw_problem, benchmark_config)
        finally:
            if sink_id is not None:
                logger.remove(sink_id)
    except Exception as exc:
        elapsed_total_s = time.time() - started_at
        token_usage = get_token_usage_snapshot(benchmark_config)
        if workflow_log_path is not None:
            logger.error(f"[Benchmark] Workflow failed for {problem_id}: {exc}")
        return BenchmarkResult(
            problem_id=problem_id,
            mode="solvita_pipeline",
            status="error",
            compile_success=False,
            passed_tests=0,
            total_tests=len(official_tests),
            elapsed_total_s=elapsed_total_s,
            llm_infer_s=0.0,
            error=str(exc),
            prompt_tokens=token_usage["prompt_tokens"],
            completion_tokens=token_usage["completion_tokens"],
            token_usage_source=token_usage["token_usage_source"],
            workflow_log_path=str(workflow_log_path) if workflow_log_path is not None else None,
        )

    elapsed_total_s = time.time() - started_at
    token_usage = {
        "prompt_tokens": int(final_state.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(final_state.get("completion_tokens", 0) or 0),
        "token_usage_source": final_state.get("token_usage_source"),
    }
    verification = final_state.get("verification") or {}
    tests_data = final_state.get("tests") or {}
    solution_code = ((final_state.get("solution") or {}).get("code") or "")
    status_str = str(final_state.get("status", "unknown"))
    used_best_solution_fallback = False
    if status_str != "success":
        best = final_state.get("best_solution") or {}
        best_code = best.get("code") or ""
        if best_code and int(best.get("passed_tests", 0)) > 0:
            solution_code = best_code
            used_best_solution_fallback = best_code != ((final_state.get("solution") or {}).get("code") or "")
    if not solution_code:
        score = {
            "compile_success": False,
            "passed_tests": 0,
            "total_tests": len(official_tests),
            "pass_rate": 0.0,
            "error": "Workflow produced no solution code",
        }
    else:
        score = score_solution_on_official_tests(
            code=solution_code,
            official_tests=official_tests,
        )

    if os.environ.get("SOLVITA_DUMP_SOLUTION") and workflow_log_path is not None:
        try:
            sol_path = workflow_log_path.with_suffix(".solution.cpp")
            sol_path.write_text(solution_code or "// no code", encoding="utf-8")
        except Exception:
            pass

    verifier_decision = verification.get("decision")
    verifier_confidence = (
        float(verification.get("confidence", 0.0) or 0.0)
        if verification.get("confidence") is not None
        else None
    )
    false_accept = (
        bool(verifier_decision == "accept" and float(score.get("pass_rate", 0.0) or 0.0) < 1.0)
        if verifier_decision is not None
        else None
    )

    if used_best_solution_fallback:
        verifier_decision = None
        verifier_confidence = None
        false_accept = None

    return BenchmarkResult(
        problem_id=problem_id,
        mode="solvita_pipeline",
        status=str(final_state.get("status", "unknown")),
        compile_success=bool(score["compile_success"]),
        passed_tests=int(score["passed_tests"]),
        total_tests=int(score["total_tests"]),
        elapsed_total_s=elapsed_total_s,
        llm_infer_s=float(final_state.get("llm_infer_s", 0.0) or 0.0),
        error=score.get("error"),
        prompt_tokens=token_usage["prompt_tokens"],
        completion_tokens=token_usage["completion_tokens"],
        token_usage_source=token_usage["token_usage_source"],
        hack_result=final_state.get("hack_result"),
        hack_passed=final_state.get("hack_passed"),
        generator_failure_kind=final_state.get("generator_failure_kind"),
        generator_failure_reason=final_state.get("generator_failure_reason"),
        workflow_log_path=str(workflow_log_path) if workflow_log_path is not None else None,
        verifier_decision=verifier_decision,
        verifier_confidence=verifier_confidence,
        false_accept=false_accept,
        full_testgen_completed=bool(tests_data.get("full_testgen_completed", False)),
    )
