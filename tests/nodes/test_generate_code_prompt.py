import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.generate_code import _build_initial_prompt, _build_patch_prompt


def test_initial_prompt_requires_resource_audit():
    prompt = _build_initial_prompt(
        problem_desc="Count something",
        algorithm="Prefix sums",
        steps=["Build data structure", "Answer queries"],
        constraints={"n": "up to 2e5", "m": "up to 2e5"},
        public_tests=[],
        generated_tests=[],
    )

    assert "Optimize for BOTH time and space complexity" in prompt
    assert "internal resource audit" in prompt
    assert "dense matrices / DP tables / adjacency tables" in prompt
    assert "adapt the implementation strategy" in prompt


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
