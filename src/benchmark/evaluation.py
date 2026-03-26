"""Helpers for scoring candidate solutions on official benchmark tests only."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from src.utils.cpp_execution import (
    ExecutionLimits,
    compile_cpp,
    run_program,
    sanitize_cpp,
)


def _normalize_output(text: str) -> str:
    return "\n".join(line.rstrip() for line in (text or "").strip().splitlines())


def score_solution_on_official_tests(
    code: str,
    official_tests: List[Dict[str, str]],
) -> Dict[str, Any]:
    total_tests = len(official_tests)
    if total_tests == 0:
        return {
            "compile_success": False,
            "passed_tests": 0,
            "total_tests": 0,
            "pass_rate": 0.0,
            "error": "No official tests provided",
        }

    try:
        sanitized_code = sanitize_cpp(code)
    except ValueError as exc:
        return {
            "compile_success": False,
            "passed_tests": 0,
            "total_tests": total_tests,
            "pass_rate": 0.0,
            "error": str(exc),
        }

    with tempfile.TemporaryDirectory(prefix="benchmark_eval_") as tmpdir:
        tmp_path = Path(tmpdir)
        src_path = tmp_path / "solution.cpp"
        exe_path = tmp_path / "solution.exe"
        src_path.write_text(sanitized_code, encoding="utf-8")

        compiled, compile_log = compile_cpp(
            src_path,
            exe_path,
            limits=ExecutionLimits.default_compile(),
        )
        if not compiled:
            return {
                "compile_success": False,
                "passed_tests": 0,
                "total_tests": total_tests,
                "pass_rate": 0.0,
                "error": compile_log,
            }

        passed_tests = 0
        for test in official_tests:
            retcode, stdout, stderr = run_program(
                exe_path,
                input_text=test.get("input", ""),
                limits=ExecutionLimits.default_run(),
                truncate_output=False,
            )
            if retcode != 0:
                return {
                    "compile_success": True,
                    "passed_tests": passed_tests,
                    "total_tests": total_tests,
                    "pass_rate": passed_tests / total_tests,
                    "error": stderr or f"Program exited with code {retcode}",
                }

            if _normalize_output(stdout) == _normalize_output(test.get("output", "")):
                passed_tests += 1

        return {
            "compile_success": True,
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "pass_rate": passed_tests / total_tests,
            "error": None,
        }
