import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import src.nodes.generate_tests as gt
from src.nodes.generate_tests import (
    build_solver_prompt,
    summarize_public_solver_failure,
    finalize_solver_certification,
    _apply_oracle_acceptance_gate,
    _build_oracle_memory_decision,
    _evaluate_oracle_memory_gate_if_ready,
)
from src.utils.test_seed_cases import (
    build_local_certified_tests,
    _count_cyclic_divisible_segments_bruteforce,
)

from src.oracle.types import AcceptedArtifactKind


def test_build_oracle_memory_decision_does_not_invent_new_primary_action() -> None:
    decision = _build_oracle_memory_decision(
        config={"trainable_memory": {"oracle_memory_mode": "oracle"}},
        selected_template_name="Top-down Memoized DP",
        gate_decision={
            "applied": True,
            "reason": "low_confidence_selected_action",
            "selected_action": "recipe.dp.memo_default",
            "replacement_action": "recipe.specialized.other",
            "candidate_action_set": [
                "recipe.dp.memo_default",
                "recipe.specialized.other",
            ],
            "exploration_flag": False,
        },
    )

    assert decision["selected_action"] == "recipe.dp.memo_default"
    assert decision["replacement_action"] is None
    assert decision["candidate_action_set"] == ["recipe.dp.memo_default"]


def test_build_oracle_memory_decision_skips_runtime_signal_when_template_unknown() -> None:
    decision = _build_oracle_memory_decision(
        config={"trainable_memory": {"oracle_memory_mode": "oracle"}},
        selected_template_name="",
        gate_decision={
            "applied": True,
            "reason": "low_confidence_selected_action",
            "selected_action": "recipe.specialized.other",
            "replacement_action": None,
            "candidate_action_set": ["recipe.specialized.other"],
            "exploration_flag": False,
        },
    )

    assert decision["applied"] is False
    assert decision["reason"] == "template_unknown"
    assert decision["selected_action"] is None
    assert decision["candidate_action_set"] == []
    assert decision["replacement_action"] is None


def test_evaluate_oracle_memory_gate_if_ready_does_not_call_runtime_gate_when_template_unknown(monkeypatch) -> None:
    called = {"value": False}

    def _unexpected_gate(**kwargs):
        called["value"] = True
        raise AssertionError("runtime gate should not be called for blank template")

    monkeypatch.setattr("src.nodes.generate_tests.decide_oracle_memory_gate", _unexpected_gate)

    decision = _evaluate_oracle_memory_gate_if_ready(
        config={"trainable_memory": {"oracle_memory_mode": "oracle"}},
        selected_template_name="",
    )

    assert called["value"] is False
    assert decision["applied"] is False
    assert decision["reason"] == "template_unknown"
    assert decision["selected_action"] is None
    assert decision["candidate_action_set"] == []


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

    tests = build_local_certified_tests(desc)

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




def test_generate_tests_wrapper_forwards_compaction_kwargs(monkeypatch):
    captured = {}

    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        captured.update(kwargs)
        return "solver reply", [], []

    monkeypatch.setattr(gt, "_generate_with_compact_retry", fake_retry)

    response, new_messages, persisted_messages = gt._call_generate_with_history(
        object(),
        gt.build_solver_prompt,
        "desc",
        {},
        [],
        "advice",
        "feedback",
        messages_history=[{"role": "assistant", "content": "old"}],
        _telemetry={"prompt_char_stats": {}},
        _stage="solver",
        _compaction_context={"node_name": "generate_tests"},
        _compaction_config={"message_compaction": {"enabled": True}},
    )

    assert response == "solver reply"
    assert new_messages == []
    assert persisted_messages == []
    assert captured["_messages_history"] == [{"role": "assistant", "content": "old"}]
    assert captured["_compaction_context"] == {"node_name": "generate_tests"}
    assert captured["_compaction_config"] == {"message_compaction": {"enabled": True}}


def test_generate_tests_wrapper_requires_history_aware_retry_signature(monkeypatch):
    seen = {}

    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        seen.setdefault("calls", 0)
        seen["calls"] += 1
        if "_messages_history" in kwargs:
            raise TypeError("fake_retry() got an unexpected keyword argument '_messages_history'")
        return "legacy reply"

    monkeypatch.setattr(gt, "_generate_with_compact_retry", fake_retry)

    with pytest.raises(TypeError):
        gt._call_generate_with_history(
            object(),
            gt.build_solver_prompt,
            "desc",
            {},
            [],
            "advice",
            "feedback",
            messages_history=[{"role": "assistant", "content": "old"}],
            _telemetry={"prompt_char_stats": {}},
            _stage="solver",
            _compaction_context={"node_name": "generate_tests"},
            _compaction_config={"message_compaction": {"enabled": True}},
        )


def test_generate_tests_node_respects_configured_no_ac_target_cap(monkeypatch, tmp_path):
    from src.graph.state import create_initial_state
    from src.nodes import generate_tests as gt

    class FakeLLM:
        @staticmethod
        def build_role_config(config, role):
            return {}

        def __init__(self, *args, **kwargs):
            pass

    class FakeCompletedProcess:
        def __init__(self):
            self.returncode = 1
            self.stderr = "generator failed"

    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        if prompt_builder is gt.build_generator_prompt:
            return '{"generator_cpp": "int main() { return 0; }"}', [], []
        if prompt_builder is gt.build_validator_prompt:
            return '{"validator_cpp": "int main() { return 0; }"}', [], []
        raise AssertionError(f"unexpected prompt builder: {prompt_builder}")

    def fake_compile_cpp(_src, _exe, include_testlib=False, diagnostic=False):
        return True, ""

    def fake_subprocess_run(*args, **kwargs):
        stdout = kwargs.get("stdout")
        if stdout is not None:
            stdout.write("")
        return FakeCompletedProcess()

    monkeypatch.setattr(gt, "UnifiedLLMClient", FakeLLM)
    monkeypatch.setattr(gt, "_generate_with_compact_retry", fake_retry)
    monkeypatch.setattr(gt, "compile_cpp", fake_compile_cpp)
    monkeypatch.setattr(gt.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(gt, "_resolve_data_root", lambda config: tmp_path)

    state = create_initial_state(
        {"description": "demo", "public_tests": [{"input": "1\n", "output": "1\n"}]},
        {
            "generate_tests_target_count": 200,
            "generate_tests_target_count_without_ac": 7,
        },
    )

    out = gt.generate_tests_node(state)

    assert out["tests"]["certified_target_count"] == 7
    assert out["tests"]["generated_tests"] == [
        {
            "input": "1\n",
            "expected_output": "1\n",
            "type": "public",
            "description": "Public test case",
            "trust_tier": "trusted",
        }
    ]


def test_generate_tests_node_uses_raw_description_for_local_certified_detection(monkeypatch, tmp_path):
    from src.graph.state import create_initial_state
    from src.nodes import generate_tests as gt

    class FakeLLM:
        @staticmethod
        def build_role_config(config, role):
            return {}

        def __init__(self, *args, **kwargs):
            pass

    class FakeCompletedProcess:
        def __init__(self):
            self.returncode = 1
            self.stderr = "generator failed"

    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        if prompt_builder is gt.build_generator_prompt:
            return '{"generator_cpp": "int main() { return 0; }"}', [], []
        if prompt_builder is gt.build_validator_prompt:
            return '{"validator_cpp": "int main() { return 0; }"}', [], []
        raise AssertionError(f"unexpected prompt builder: {prompt_builder}")

    def fake_compile_cpp(_src, _exe, include_testlib=False, diagnostic=False):
        return True, ""

    def fake_subprocess_run(*args, **kwargs):
        stdout = kwargs.get("stdout")
        if stdout is not None:
            stdout.write("")
        return FakeCompletedProcess()

    monkeypatch.setattr(gt, "UnifiedLLMClient", FakeLLM)
    monkeypatch.setattr(gt, "_generate_with_compact_retry", fake_retry)
    monkeypatch.setattr(gt, "compile_cpp", fake_compile_cpp)
    monkeypatch.setattr(gt.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(gt, "_resolve_data_root", lambda config: tmp_path)

    raw_description = (
        "Denote a cyclic sequence of size n as an array. You are given an array obtained from concatenating m copies. "
        "Find the number of different segments where the sum of elements in the segment is divisible by k. "
        "Two segments are considered different if the set of indices are different."
    )
    state = create_initial_state(
        {"description": raw_description, "public_tests": []},
        {
            "generate_tests_target_count": 200,
            "generate_tests_target_count_without_ac": 7,
        },
    )
    state["problem"]["canonical"] = {
        "objective": "Count something generic",
        "inputs": {"n": "int"},
        "outputs": {"answer": "int"},
        "constraints": {"n": "large"},
    }

    out = gt.generate_tests_node(state)

    assert any(test["type"] == "edge" for test in out["tests"]["generated_tests"])
    assert any(test["trust_tier"] == "trusted" for test in out["tests"]["generated_tests"])
