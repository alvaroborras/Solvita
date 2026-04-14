"""Compile C++ and run user-provided tests (Solvita utilities)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from skill_graph_train.bootstrap import ensure_import_paths

ensure_import_paths()

from src.nodes.compile_code import prepare_executable  # noqa: E402
from src.utils.cpp_execution import ExecutionLimits, run_program  # noqa: E402
from src.utils.output_judging import judge_output_against_certified_expected  # noqa: E402
from skill_graph.types import Outcome  # noqa: E402


def compile_solution(code: str, diagnostic: bool = False) -> Tuple[bool, Path | None, List[str]]:
    """Compile ``code`` to a temp executable. Returns (ok, exe_path, errors)."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="sgt_compile_"))
    limits = ExecutionLimits.diagnostic_compile() if diagnostic else ExecutionLimits.default_compile()
    exe_path, errors = prepare_executable(code, "C++", tmp_dir, diagnostic, limits)
    return bool(exe_path), exe_path, errors


def run_user_tests(
    exe_path: Path,
    tests: List[Dict[str, Any]],
    checker_exe: Path | None = None,
) -> Tuple[float, List[Dict[str, Any]], Outcome]:
    """
    Run each test dict with keys ``input`` and ``expected_output`` (Solvita ``run_tests`` convention).

    Returns ``(pass_rate, test_results, coarse_outcome)``.
    """
    if not tests:
        return 0.0, [], Outcome.WRONG_ANSWER

    passed = 0
    results: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        for i, test in enumerate(tests):
            test_input = test.get("input", "")
            if isinstance(test_input, list):
                test_input = "\n".join(str(x) for x in test_input)
            expected = test.get("expected_output") or test.get("output") or ""
            if isinstance(expected, list):
                expected = "\n".join(str(x) for x in expected)
            expected = str(expected).strip()

            try:
                retcode, stdout, stderr = run_program(
                    exe_path,
                    input_text=test_input,
                    limits=ExecutionLimits.default_run(),
                )

                class _R:
                    def __init__(self, rc: int, so: str, se: str):
                        self.returncode = rc
                        self.stdout = so
                        self.stderr = se

                result = _R(retcode, stdout, stderr)
                actual = result.stdout.strip()
                err_msg = result.stderr if result.stderr else None

                input_file = tmp_path / f"input_{i}.txt"
                output_file = tmp_path / f"output_{i}.txt"
                answer_file = tmp_path / f"answer_{i}.txt"
                input_file.write_text(test_input, encoding="utf-8")
                output_file.write_text(result.stdout, encoding="utf-8")
                answer_file.write_text(expected, encoding="utf-8")

                passed_test, judge_msg = judge_output_against_certified_expected(
                    actual_output=result.stdout,
                    expected_output=expected,
                    checker_exe=checker_exe,
                    input_path=input_file,
                    output_path=output_file,
                    answer_path=answer_file,
                )
                if not passed_test and judge_msg:
                    err_msg = f"{err_msg or ''}\n{judge_msg}".strip()

                if passed_test:
                    passed += 1

                results.append(
                    {
                        "test_id": i,
                        "input": test_input,
                        "expected": expected,
                        "actual": actual,
                        "passed": passed_test,
                        "error": err_msg,
                    }
                )
            except subprocess.TimeoutExpired:
                results.append(
                    {
                        "test_id": i,
                        "input": test_input,
                        "expected": expected,
                        "actual": "",
                        "passed": False,
                        "error": "Timeout",
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "test_id": i,
                        "input": test_input,
                        "expected": expected,
                        "actual": "",
                        "passed": False,
                        "error": str(e),
                    }
                )

    total = len(tests)
    pass_rate = passed / total if total else 0.0
    outcome = outcome_from_results(pass_rate, results)
    return pass_rate, results, outcome


def outcome_from_results(pass_rate: float, results: List[Dict[str, Any]]) -> Outcome:
    """Map sandbox results to skill_graph :class:`Outcome` (coarse)."""
    if pass_rate >= 1.0 - 1e-9:
        return Outcome.ACCEPTED
    for r in results:
        if (r.get("error") or "") == "Timeout":
            return Outcome.TIME_LIMIT
    if pass_rate > 0.0:
        return Outcome.PARTIAL
    return Outcome.WRONG_ANSWER
