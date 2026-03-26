"""Strict single-pass GPT-5.2 benchmark adapter."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from src.benchmark.evaluation import score_solution_on_official_tests
from src.benchmark.types import BenchmarkResult
from src.llm import UnifiedLLMClient
from src.llm.token_usage import ensure_token_usage_accumulator
from src.utils.cpp_execution import sanitize_cpp


def build_single_pass_prompt(raw_problem: Dict[str, Any]) -> str:
    description = raw_problem.get("description", "")
    time_limit = raw_problem.get("time_limit")
    space_limit = raw_problem.get("space_limit")
    public_tests = raw_problem.get("public_tests", []) or []

    public_block = []
    for idx, test in enumerate(public_tests, 1):
        public_block.append(f"Sample {idx} Input:\n{test.get('input', '')}")
        public_block.append(f"Sample {idx} Output:\n{test.get('output', '')}")

    sample_text = "\n\n".join(public_block) if public_block else "No public samples provided."

    return f"""Solve this competitive programming problem in a single pass.

Problem Description:
{description}

Constraints:
- Time limit: {time_limit} ms
- Memory limit: {space_limit} MB

Public Samples:
{sample_text}

Requirements:
- Return ONLY complete C++17 source code.
- Do not include markdown fences.
- Include all required headers.
- Read from stdin and write to stdout.
- Produce a correct and efficient solution.
"""


def build_gpt52_single_pass_config(config: Dict[str, Any] | None) -> Dict[str, Any]:
    single_pass_config = dict(config or {})
    single_pass_config["model"] = "gpt-5.2"
    ensure_token_usage_accumulator(single_pass_config)
    return single_pass_config


def _get_usage_snapshot(llm: Any) -> Dict[str, Any]:
    getter = getattr(llm, "get_usage_snapshot", None)
    if callable(getter):
        return getter()
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "token_usage_source": "untracked",
    }


def _write_single_pass_artifacts(
    config: Dict[str, Any],
    problem_id: str,
    prompt: str,
    raw_response: str,
    sanitized_code: str | None = None,
) -> None:
    output_dir = config.get("benchmark_output_dir")
    if not output_dir:
        return
    root = Path(output_dir) / "artifacts" / "gpt52_single_pass"
    root.mkdir(parents=True, exist_ok=True)
    stem = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in problem_id).strip("._") or "unknown"
    (root / f"{stem}.prompt.txt").write_text(prompt, encoding="utf-8")
    (root / f"{stem}.raw.txt").write_text(raw_response, encoding="utf-8")
    if sanitized_code is not None:
        (root / f"{stem}.cpp").write_text(sanitized_code, encoding="utf-8")


def run_gpt52_single_pass_case(
    problem_payload: Dict[str, Any],
    config: Dict[str, Any] | None = None,
) -> BenchmarkResult:
    problem_id = str(problem_payload.get("problem_id", "unknown"))
    raw_problem = problem_payload.get("raw_problem", {})
    official_tests = list(problem_payload.get("official_tests", []) or [])
    llm_config = build_gpt52_single_pass_config(config)
    llm = UnifiedLLMClient(llm_config)
    prompt = build_single_pass_prompt(raw_problem)

    started_at = time.time()
    llm_started_at = time.time()
    raw_response = llm.generate(prompt, model="gpt-5.2")
    llm_infer_s = time.time() - llm_started_at
    usage = _get_usage_snapshot(llm)
    _write_single_pass_artifacts(llm_config, problem_id, prompt, raw_response)

    if not raw_response.strip():
        elapsed_total_s = time.time() - started_at
        return BenchmarkResult(
            problem_id=problem_id,
            mode="gpt52_single_pass",
            status="error",
            compile_success=False,
            passed_tests=0,
            total_tests=len(official_tests),
            elapsed_total_s=elapsed_total_s,
            llm_infer_s=llm_infer_s,
            error="Empty model response",
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            token_usage_source=usage.get("token_usage_source"),
        )

    try:
        candidate_code = sanitize_cpp(raw_response)
    except ValueError as exc:
        elapsed_total_s = time.time() - started_at
        return BenchmarkResult(
            problem_id=problem_id,
            mode="gpt52_single_pass",
            status="error",
            compile_success=False,
            passed_tests=0,
            total_tests=len(official_tests),
            elapsed_total_s=elapsed_total_s,
            llm_infer_s=llm_infer_s,
            error=str(exc),
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            token_usage_source=usage.get("token_usage_source"),
        )
    _write_single_pass_artifacts(llm_config, problem_id, prompt, raw_response, sanitized_code=candidate_code)

    score = score_solution_on_official_tests(
        code=candidate_code,
        official_tests=official_tests,
    )
    elapsed_total_s = time.time() - started_at
    return BenchmarkResult(
        problem_id=problem_id,
        mode="gpt52_single_pass",
        status="success" if score["compile_success"] else "error",
        compile_success=bool(score["compile_success"]),
        passed_tests=int(score["passed_tests"]),
        total_tests=int(score["total_tests"]),
        elapsed_total_s=elapsed_total_s,
        llm_infer_s=llm_infer_s,
        error=score.get("error"),
        prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        token_usage_source=usage.get("token_usage_source"),
    )
