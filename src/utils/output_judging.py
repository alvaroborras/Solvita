"""Helpers for judging candidate outputs against certified expected outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from src.utils.cpp_execution import run_checker


def judge_output_against_certified_expected(
    *,
    actual_output: str,
    expected_output: str,
    checker_exe: Optional[Path] = None,
    input_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    answer_path: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    actual = str(actual_output or "").strip()
    expected = str(expected_output or "").strip()

    if actual == expected:
        return True, None

    mismatch_msg = f"Expected '{expected[:50]}...', got '{actual[:50]}...'"

    if (
        checker_exe
        and checker_exe.exists()
        and input_path is not None
        and output_path is not None
        and answer_path is not None
    ):
        chk_ok, chk_msg = run_checker(checker_exe, input_path, output_path, answer_path)
        if chk_ok:
            return (
                False,
                mismatch_msg
                + " Checker accepted a conflicting output, but certified expected output takes precedence.",
            )
        return False, f"{mismatch_msg} Checker: {chk_msg}"

    return False, mismatch_msg
