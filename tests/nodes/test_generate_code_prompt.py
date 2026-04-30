import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import src.nodes.generate_code as generate_code_module
from src.llm.unified_client import PromptTooLongError
from src.nodes.generate_code import (
    _build_initial_prompt,
    _build_patch_prompt,
    _build_repair_decision_prompt,
    _build_verification_set,
    _call_generate_with_history,
    _format_aggregate_failures_text,
    _generate_with_compact_retry,
    _parse_repair_mode_decision,
)


def test_initial_prompt_requires_resource_audit():
    prompt = _build_initial_prompt(
        problem_desc="Count something",
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        constraints={"n": "up to 2e5", "m": "up to 2e5"},
        public_tests=[],
        generated_tests=[],
    )

    # New skill-based prompt: check for HARD-GATE, design-before-code, and complexity audit
    assert "HARD-GATE" in prompt
    assert "Design Before Implementation" in prompt
    assert "Complexity" in prompt
    assert "Memory" in prompt or "memory limit" in prompt.lower()
    assert "adapt" in prompt


def test_initial_prompt_includes_self_validation_feedback():
    prompt = _build_initial_prompt(
        problem_desc="Count something",
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        constraints={},
        public_tests=[],
        generated_tests=[],
        self_validation_feedback="Self-validation failed: 2 issues in 2/4 cases tested:\n\n  Wrong answer on test public_0:\n    Input: 1",
    )

    assert "Self-validation failed: 2 issues in 2/4 cases tested:" in prompt
    assert "Wrong answer on test public_0" in prompt


def test_patch_prompt_requires_rechecking_space_complexity():
    prompt = _build_patch_prompt(
        prev_code="int main() { return 0; }\n",
        problem_desc="Count something",
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        specific_failures=[],
        suggested_fixes=[],
        feedback_text="memory issue on large inputs",
    )

    assert "Re-check BOTH time and space complexity" in prompt
    assert "dangerous product of input dimensions" in prompt
    assert "not implementable within the stated limits" in prompt


def test_patch_prompt_includes_aggregate_failures_block():
    aggregate_text = _format_aggregate_failures_text(
        {
            "total_failed": 70,
            "judge_status_counts": {"wrong_answer": 60, "timeout": 10},
            "error_type_counts": {"wrong_answer": 60, "timeout": 10},
            "repair_subtype_counts": {"wa_numeric_too_small": 48, "tle_full_input_only": 10},
            "input_length": {"min": 4, "avg": 42.5, "max": 300},
            "numeric_diff": {"count": 8, "avg_diff": -1.5, "min_diff": -7, "max_diff": 1},
            "representative_examples": {
                "wrong_answer": [
                    {
                        "input": "1 2 3",
                        "expected": "7",
                        "actual": "6",
                        "error": "mismatch",
                        "repair_subtype": "wa_numeric_too_small",
                    }
                ]
            },
        }
    )

    prompt = _build_patch_prompt(
        prev_code="int main() { return 0; }\n",
        problem_desc="Count something",
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        specific_failures=[],
        suggested_fixes=[],
        feedback_text="analysis",
        aggregate_failures_text=aggregate_text,
    )

    assert "Aggregate failure summary across internal tests:" in prompt
    assert "Total failed tests: 70" in prompt
    assert "Judge status counts:" in prompt
    assert "wrong_answer: 60" in prompt
    assert "timeout: 10" in prompt
    assert "Repair subtype counts:" in prompt
    assert "wa_numeric_too_small: 48" in prompt
    assert "Repair subtype: wa_numeric_too_small" in prompt


def test_repair_decision_prompt_requires_scope_judgment_first():
    prompt = _build_repair_decision_prompt(
        prev_code="int main() { return 0; }\n",
        problem_desc="Count something",
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        specific_failures=[],
        suggested_fixes=[],
        feedback_text="analysis",
        aggregate_failures_text="",
        diagnostic_text="",
    )

    assert "localized bug or a systemic/global flaw" in prompt
    assert "objective evidence" in prompt
    assert '"mode":"patch|full_regen"' in prompt


def test_parse_repair_mode_decision_defaults_to_patch_on_invalid_json():
    assert _parse_repair_mode_decision("not-json") == {
        "mode": "patch",
        "confidence": "low",
        "reason": "fallback-to-patch",
    }


def test_parse_repair_mode_decision_normalizes_invalid_mode_to_patch():
    assert _parse_repair_mode_decision(json.dumps({"mode": "weird", "confidence": "high", "reason": "x"})) == {
        "mode": "patch",
        "confidence": "high",
        "reason": "x",
    }

def test_initial_prompt_truncates_large_context():
    prompt = _build_initial_prompt(
        problem_desc="D" * 20000,
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        constraints={"payload": "C" * 8000},
        public_tests=[{"input": "I" * 3000, "output": "O" * 3000} for _ in range(5)],
        generated_tests=[{"input": "G" * 3000} for _ in range(5)],
    )

    assert "[TRUNCATED" in prompt
    assert len(prompt) < 30000


def test_patch_prompt_truncates_large_context():
    prompt = _build_patch_prompt(
        prev_code="int main() {\n" + ("x++;\\n" * 10000) + "}\n",
        problem_desc="P" * 16000,
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        specific_failures=[{"input": "I" * 2000, "expected": "E" * 1000, "output": "O" * 1000, "details": "D" * 1000}],
        suggested_fixes=["fix"],
        feedback_text="F" * 8000,
    )

    assert "[TRUNCATED" in prompt
    assert len(prompt) < 40000


def test_generate_code_wrapper_forwards_compaction_kwargs(monkeypatch):
    captured = {}

    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        captured.update(kwargs)
        return "reply", [], []

    monkeypatch.setattr(generate_code_module, "_generate_with_compact_retry", fake_retry)

    response, new_messages, persisted_messages = _call_generate_with_history(
        object(),
        _build_initial_prompt,
        "Count something",
        "Prefix sums",
        ["Build", "Answer"],
        {},
        [],
        [],
        messages_history=[{"role": "assistant", "content": "old"}],
        _stage="generate_code.initial",
        _compaction_context={"node_name": "generate_code"},
        _compaction_config={"message_compaction": {"enabled": True}},
    )

    assert response == "reply"
    assert new_messages == []
    assert persisted_messages == []
    assert captured["_messages_history"] == [{"role": "assistant", "content": "old"}]
    assert captured["_compaction_context"] == {"node_name": "generate_code"}
    assert captured["_compaction_config"] == {"message_compaction": {"enabled": True}}


def test_generate_code_wrapper_requires_history_aware_retry_signature(monkeypatch):
    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        raise TypeError("fake_retry() got an unexpected keyword argument '_messages_history'")

    monkeypatch.setattr(generate_code_module, "_generate_with_compact_retry", fake_retry)

    with pytest.raises(TypeError):
        _call_generate_with_history(
            object(),
            _build_initial_prompt,
            "Count something",
            "Prefix sums",
            ["Build", "Answer"],
            {},
            [],
            [],
            messages_history=[{"role": "assistant", "content": "old"}],
            _stage="generate_code.initial",
            _compaction_context={"node_name": "generate_code"},
            _compaction_config={"message_compaction": {"enabled": True}},
        )


def test_generate_code_logs_prompt_body(monkeypatch):
    class FakeLLM:
        def generate(self, prompt, **kwargs):
            return "int main() { return 0; }"

    messages = []
    monkeypatch.setattr(generate_code_module.logger, "debug", lambda msg: messages.append(msg))

    llm = FakeLLM()
    _generate_with_compact_retry(
        llm,
        _build_initial_prompt,
        "Count something",
        "Prefix sums",
        ["Build", "Answer"],
        {},
        [],
        [],
        _stage="generate_code.initial",
    )

    assert messages
    assert "[PROMPT_BODY:generate_code.initial] compact=0" in messages[0]
    assert "Count something" in messages[0]


def test_generate_code_retries_with_compact_prompt_on_prompt_too_long():
    class FakeLLM:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                raise PromptTooLongError("prompt is too long: maximum context length")
            return "int main() { return 0; }"

    llm = FakeLLM()
    result = _generate_with_compact_retry(
        llm,
        _build_initial_prompt,
        "P" * 20000,
        "Prefix sums",
        ["Build", "Answer"],
        {"payload": "C" * 8000},
        [{"input": "I" * 3000, "output": "O" * 3000} for _ in range(5)],
        [{"input": "G" * 3000} for _ in range(5)],
        memory_advice="A" * 4000,
    )

    assert result == "int main() { return 0; }"
    assert len(llm.prompts) == 2
    assert "[TRUNCATED" in llm.prompts[1]



# ── Multi-turn prompt builder tests ──────────────────────────────────────────

def test_think_prompt_forbids_code_and_has_required_sections():
    """Think prompt must forbid C++ code and include algorithm/complexity/trace sections."""
    from src.nodes.generate_code import _build_think_prompt

    prompt = _build_think_prompt(
        problem_desc="Given N integers, find the maximum subarray sum.",
        algorithm="",
        steps=[],
        constraints={"time_limit": 2000, "space_limit": 256},
        public_tests=[{"input": "5\n-2 1 -3 4 -1", "output": "4"}],
        abstract_tags_level2_block="",
        memory_advice="",
    )

    lower = prompt.lower()
    assert "do not" in lower or "no code" in lower, "Think prompt must forbid code output"
    assert "algorithm" in lower
    assert "complexity" in lower or "tle" in lower or "10^8" in lower
    assert "sample" in lower or "trace" in lower
    assert "sketch" in lower or "implementation" in lower
    assert "solution.cpp" not in prompt
    assert "```cpp" not in prompt


def test_think_prompt_includes_algorithm_hint():
    """Think prompt should include the algorithm hint when provided."""
    from src.nodes.generate_code import _build_think_prompt

    prompt = _build_think_prompt(
        problem_desc="Sum array elements",
        algorithm="Prefix sums",
        steps=["Build prefix array"],
        constraints={"time_limit": 1000, "space_limit": 256},
        public_tests=[],
        abstract_tags_level2_block="",
        memory_advice="",
    )
    assert "Prefix sums" in prompt


def test_code_only_prompt_has_no_hard_gate():
    """code_only prompt must not contain the HARD-GATE design block."""
    from src.nodes.generate_code import _build_code_only_prompt

    prompt = _build_code_only_prompt(
        problem_desc="Sum array elements.",
        constraints={"time_limit": 1000, "space_limit": 256},
        public_tests=[{"input": "3\n1 2 3", "output": "6"}],
        generated_tests=[],
        memory_advice="",
        self_validation_feedback="",
    )

    assert "HARD-GATE" not in prompt
    assert "Do NOT write any C++ code until" not in prompt
    assert "C++17" in prompt or "c++17" in prompt.lower()
    assert "SELF_VALIDATION_BLOCK" not in prompt  # placeholder rendered away
    assert "Solution" in prompt
