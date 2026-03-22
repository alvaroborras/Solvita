import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.generate_tests import (
    build_solver_prompt,
    summarize_public_solver_failure,
    finalize_solver_certification,
)


def test_build_solver_prompt_attempts_escalate_strategy():
    prompt1 = build_solver_prompt("desc", {}, [], "", "", attempt=1)
    prompt2 = build_solver_prompt("desc", {}, [], "", "Solver crashed on public test 0: Time Limit Exceeded", attempt=2)
    prompt3 = build_solver_prompt("desc", {}, [], "", "Previous attempt timed out", attempt=3)

    assert "independent reference solution" in prompt1
    assert "avoid factorial or exponential" in prompt1.lower()
    assert "must run within the certification limits" in prompt2.lower()
    assert "do not use factorial or exponential search" in prompt2.lower()
    assert "robust reference solution" in prompt3.lower()
    assert "debug prints to stderr" in prompt3.lower()


def test_summarize_public_solver_failure_includes_case_details():
    feedback = summarize_public_solver_failure(
        test_id="public_0",
        test_input="5 2\nAA\nAB\n",
        expected="1 2\n",
        actual="2 1\n",
        error="Checker: wrong order",
        diagnostic_info="",
    )

    assert "Wrong answer on test public_0" in feedback
    assert "5 2" in feedback
    assert "2 1" in feedback
    assert "Checker: wrong order" in feedback


def test_finalize_solver_certification_keeps_best_partial_in_production():
    result = finalize_solver_certification(
        training_mode=False,
        original_input_count=5,
        current_partial_inputs=["in1", "in2"],
        current_partial_outputs=["out1", "out2"],
        best_partial_inputs=["in1"],
        best_partial_outputs=["out1"],
        solver_ok=False,
    )

    assert result["accepted"] is True
    assert result["inputs"] == ["in1", "in2"]
    assert result["outputs"] == ["out1", "out2"]
    assert "PARTIALLY CERTIFIED" in result["message"]
