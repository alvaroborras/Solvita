import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.generate_tests import (
    build_solver_prompt,
    summarize_public_solver_failure,
    finalize_solver_certification,
    _build_local_certified_tests,
    _count_cyclic_divisible_segments_bruteforce,
    _apply_oracle_acceptance_gate,
)
from src.oracle.types import AcceptedArtifactKind


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


def test_build_solver_prompt_for_cyclic_sum_mentions_lifted_boundary():
    desc = (
        "Denote a cyclic sequence. You are given an array obtained by concatenating m copies. "
        "Find the number of different segments where the sum of elements in the segment is divisible by k. "
        "Two segments are considered different if the set of indices are different, even on the same set of indices."
    )

    prompt = build_solver_prompt(desc, {}, [], "", "", attempt=1)

    assert "wrap-around vs non-wrap" in prompt
    assert "lifted boundary at position N" in prompt
    assert "doubled-array" in prompt


def test_cyclic_sum_bruteforce_helper_matches_known_counterexample():
    assert _count_cyclic_divisible_segments_bruteforce(1, 3, 2, [1]) == 3


def test_build_local_certified_tests_includes_wrap_counterexamples():
    desc = (
        "Denote a cyclic sequence of size n as an array. You are given an array obtained from concatenating m copies. "
        "Find the number of different segments where the sum of elements in the segment is divisible by k. "
        "Two segments are considered different if the set of indices are different."
    )

    tests = _build_local_certified_tests(desc)

    assert len(tests) >= 3
    assert tests[0]["input"] == "1 3 2\n1\n"
    assert tests[0]["output"] == "3\n"
    assert all(test["type"] == "edge" for test in tests)


def test_safe_mode_prefers_abstain_when_confidence_missing():
    artifact = _apply_oracle_acceptance_gate(
        route="exact_single_answer",
        generated_inputs=["1\n"],
        generated_outputs=["1\n"],
        confidence=0.0,
        threshold=0.95,
        trusted_checker_provenance=None,
    )
    assert artifact is None


def test_route_b_requires_checker_bundle_when_accepted():
    artifact = _apply_oracle_acceptance_gate(
        route="trusted_checker_backed_multi_answer",
        generated_inputs=["1\n"],
        generated_outputs=["2 1\n"],
        confidence=1.0,
        threshold=0.80,
        trusted_checker_provenance={"kind": "official_checker", "source_id": "dataset://checker/demo"},
    )
    assert artifact is not None
    assert artifact["kind"] == AcceptedArtifactKind.CHECKER_BUNDLE.value
