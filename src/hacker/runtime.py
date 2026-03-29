from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.cpp_execution import ExecutionLimits, run_checker, run_program
from src.utils.verdict import VerdictStatus, evaluate_verdict


def execute_hack_candidate(
    *,
    exe_path: Path,
    generated_input: str,
    expected_output: str = "",
    checker_exe: Optional[Path] = None,
    run_program_fn=None,
    run_checker_fn=None,
    evaluate_verdict_fn=None,
) -> Dict[str, Any]:
    if run_program_fn is None:
        run_program_fn = run_program
    if run_checker_fn is None:
        run_checker_fn = run_checker
    if evaluate_verdict_fn is None:
        evaluate_verdict_fn = evaluate_verdict

    failures: List[Dict[str, Any]] = []
    sandbox_verdicts: List[Dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        try:
            ret_code, stdout, stderr = run_program_fn(
                exe_path,
                input_text=generated_input,
                limits=ExecutionLimits.default_run(),
            )
        except Exception as e:
            failures.append({"type": "System Error", "input": generated_input, "details": str(e)})
            sandbox_verdicts.append(evaluate_verdict_fn(True, -1, False, stderr=str(e)))
            return {
                "hack_passed": False,
                "hack_failures": failures,
                "sandbox_verdicts": sandbox_verdicts,
                "compile_failures": 0,
            }

        is_timeout = ret_code == 124
        actual = stdout.strip()
        chk_ok = None
        output_match = None
        chk_msg = ""

        if not is_timeout and ret_code == 0:
            if checker_exe and checker_exe.exists():
                input_file = tmp_path / "hack.in"
                output_file = tmp_path / "hack.out"
                answer_file = tmp_path / "hack.ans"
                input_file.write_text(generated_input, encoding="utf-8")
                output_file.write_text(stdout, encoding="utf-8")
                answer_file.write_text(expected_output, encoding="utf-8")
                chk_ok, chk_msg = run_checker_fn(checker_exe, input_file, output_file, answer_file)
            else:
                output_match = (actual == expected_output.strip()) if expected_output.strip() else None

        verdict = evaluate_verdict_fn(
            validator_ok=True,
            exec_returncode=ret_code,
            exec_timeout=is_timeout,
            checker_ok=chk_ok,
            output_matches_expected=output_match,
            stderr=stderr,
        )
        sandbox_verdicts.append(verdict)

        if verdict["verdict"] == VerdictStatus.VALID_AND_BREAK.value:
            failures.append(
                {
                    "type": verdict["failure_type"],
                    "input": generated_input,
                    "output": actual if ret_code == 0 else stderr,
                    "expected": expected_output.strip(),
                    "details": chk_msg or verdict["details"],
                }
            )

    return {
        "hack_passed": not failures,
        "hack_failures": failures,
        "sandbox_verdicts": sandbox_verdicts,
        "compile_failures": 0,
    }
