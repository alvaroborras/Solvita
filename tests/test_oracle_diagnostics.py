import pytest
from pathlib import Path
from src.nodes.generate_tests import (
    format_solver_feedback,
    build_solver_prompt,
    build_generator_prompt,
    build_validator_prompt,
    build_checker_prompt,
    _compute_certification_ratio,
    _generate_with_compact_retry,
    _append_distinct_generated_input,
    _resolve_selected_family_id,
    _validate_checker_on_public_tests,
)
from src.utils.output_judging import judge_output_against_certified_expected
from src.nodes.analyze_feedback import _analyze_compilation_errors
from src.llm.unified_client import PromptTooLongError
from src.oracle.types import OraclePlan, OracleRoute

def test_format_solver_feedback_with_asan():
    failed = [
        {"type": "runtime_error", "id": 0, "error": "Segmentation fault", "input": "5\n1 2 3 4 5"}
    ]
    asan_output = "==1234==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x..."
    feedback = format_solver_feedback(failed, 1, 1, diagnostic_info=asan_output)
    
    assert "AddressSanitizer" in feedback
    assert "heap-buffer-overflow" in feedback
    assert "Your code failed 1 out of 1 cases" in feedback

def test_format_solver_feedback_with_traces():
    failed = [
        {
            "type": "wrong_answer", 
            "id": 1, 
            "input": "3", 
            "output": "10", 
            "stderr": "TRACE: depth=0\nTRACE: calling dfs(1)\nsome other log\nTRACE: returning 5"
        }
    ]
    feedback = format_solver_feedback(failed, 1, 1)
    
    assert "Execution Traces (from stderr):" in feedback
    assert "TRACE: depth=0" in feedback
    assert "TRACE: calling dfs(1)" in feedback
    assert "TRACE: returning 5" in feedback
    assert "some other log" not in feedback

def test_build_solver_prompt_with_traces():
    # Attempt 1 should not have trace instruction
    prompt1 = build_solver_prompt("desc", {}, [], "{}", "fail", attempt=1)
    assert "TRACE:" not in prompt1
    
    # Attempt 3 should have trace instruction
    prompt3 = build_solver_prompt("desc", {}, [], "{}", "fail", attempt=3)
    assert "TRACE:" in prompt3
    assert "std::cerr" in prompt3


def test_truncate_output():
    from src.utils.cpp_execution import _truncate_output
    # Under limit
    assert _truncate_output("abc", 10) == "abc"
    # Over limit
    long_str = "A" * 100
    truncated = _truncate_output(long_str, 20)
    assert "[TRUNCATED 80 CHARS]" in truncated
    assert truncated.startswith("A" * 10)
    assert truncated.endswith("A" * 10)


def test_format_solver_feedback_with_many_traces():
    # Simulate 100 trace lines
    trace_lines = [f"TRACE: step {i}" for i in range(100)]
    stderr = "\n".join(trace_lines)
    # total_run=1, total_verify=1
    failed = [{"type": "wrong_answer", "id": 1, "stderr": stderr}]
    
    feedback = format_solver_feedback(failed, 1, 1)
    
    # Check for sampling tags
    assert "[TRACED BUT SAMPLED/SKIPPED]" in feedback
    # Should see first and last parts
    assert "TRACE: step 0" in feedback
    assert "TRACE: step 99" in feedback
    # Should see middle part (around step 50)
    assert "TRACE: step 50" in feedback


def test_format_solver_feedback_compresses_large_asan_block():
    failed = [
        {"type": "runtime_error", "id": 0, "error": "Segmentation fault", "input": "1\n"}
    ]
    asan_lines = [f"asan line {i}" for i in range(80)]
    asan_lines[3] = "==1234==ERROR: AddressSanitizer: heap-buffer-overflow"
    diagnostic_info = "\n".join(asan_lines)

    feedback = format_solver_feedback(failed, 1, 1, diagnostic_info=diagnostic_info)

    assert "AddressSanitizer" in feedback
    assert "asan line 0" in feedback
    assert "asan line 79" in feedback
    assert "[ASAN TRUNCATED]" in feedback
    assert len(feedback) < len(diagnostic_info) + 250


def test_format_solver_feedback_truncates_long_checker_message():
    failed = [
        {
            "type": "wrong_answer",
            "id": 1,
            "input": "3\n1 2 3\n",
            "output": "999",
            "error": "X" * 1200,
        }
    ]

    feedback = format_solver_feedback(failed, 1, 1)

    assert "Checker message:" in feedback
    assert "[TRUNCATED" in feedback
    assert len(feedback) < 1200


def test_build_generator_prompt_truncates_large_context():
    huge_desc = "D" * 20000
    public_tests = [{"input": "I" * 5000, "output": "O" * 5000} for _ in range(8)]

    prompt = build_generator_prompt(huge_desc, {"n": "1e5", "blob": "X" * 6000}, public_tests, "")

    assert "[TRUNCATED" in prompt
    assert len(prompt) < 25000


def test_build_generator_prompt_forbids_fixed_single_case_generators():
    prompt = build_generator_prompt("desc", {"n": "1e5"}, [], "")

    assert "Do NOT hardcode one fixed test case" in prompt
    assert "different seeds" in prompt
    assert "multiple distinct valid outputs" in prompt


def test_append_distinct_generated_input_rejects_duplicates():
    generated_inputs = []
    seen_inputs = set()

    assert _append_distinct_generated_input(generated_inputs, seen_inputs, "1 2 3\n4 5 6\n") is True
    assert _append_distinct_generated_input(generated_inputs, seen_inputs, "1 2 3\n4 5 6\n\n") is False
    assert _append_distinct_generated_input(generated_inputs, seen_inputs, "7 8 9\n") is True

    assert generated_inputs == ["1 2 3\n4 5 6\n", "7 8 9\n"]
    assert seen_inputs == {"1 2 3\n4 5 6\n", "7 8 9\n"}


def test_validate_checker_on_public_tests_rejects_trailing_garbage(monkeypatch, tmp_path):
    checker_exe = tmp_path / "checker.exe"
    checker_exe.write_text("", encoding="utf-8")
    calls = []

    def fake_run_checker(_checker, _input_path, output_path, _answer_path):
        text = output_path.read_text(encoding="utf-8")
        calls.append(text)
        if "__CHECKER_NEGATIVE_TOKEN__" in text:
            return True, "incorrectly accepted"
        return True, "ok"

    monkeypatch.setattr("src.nodes.generate_tests.run_checker", fake_run_checker)

    ok, message = _validate_checker_on_public_tests(
        checker_exe,
        [{"input": "1\n", "output": "42\n"}],
        tmp_path,
    )

    assert ok is False
    assert "trailing garbage" in message
    assert len(calls) == 2


def test_judge_output_against_certified_expected_ignores_conflicting_checker(monkeypatch, tmp_path):
    checker_exe = tmp_path / "checker.exe"
    checker_exe.write_text("", encoding="utf-8")
    input_path = tmp_path / "input.txt"
    output_path = tmp_path / "output.txt"
    answer_path = tmp_path / "answer.txt"
    input_path.write_text("1\n", encoding="utf-8")
    output_path.write_text("2\n", encoding="utf-8")
    answer_path.write_text("1\n", encoding="utf-8")

    monkeypatch.setattr("src.utils.output_judging.run_checker", lambda *args, **kwargs: (True, "ok"))

    passed, message = judge_output_against_certified_expected(
        actual_output="2\n",
        expected_output="1\n",
        checker_exe=checker_exe,
        input_path=input_path,
        output_path=output_path,
        answer_path=answer_path,
    )

    assert passed is False
    assert "certified expected output takes precedence" in message


def test_judge_output_against_certified_expected_skips_checker_on_exact_match(monkeypatch, tmp_path):
    checker_exe = tmp_path / "checker.exe"
    checker_exe.write_text("", encoding="utf-8")
    input_path = tmp_path / "input.txt"
    output_path = tmp_path / "output.txt"
    answer_path = tmp_path / "answer.txt"
    input_path.write_text("1\n", encoding="utf-8")
    output_path.write_text("1\n", encoding="utf-8")
    answer_path.write_text("1\n", encoding="utf-8")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("checker should not run when actual matches certified expected output")

    monkeypatch.setattr("src.utils.output_judging.run_checker", fail_if_called)

    passed, message = judge_output_against_certified_expected(
        actual_output="1\n",
        expected_output="1\n",
        checker_exe=checker_exe,
        input_path=input_path,
        output_path=output_path,
        answer_path=answer_path,
    )

    assert passed is True
    assert message is None


def test_other_prompt_builders_truncate_large_context():
    huge_desc = "P" * 20000
    huge_constraints = {"payload": "C" * 8000}
    public_tests = [{"input": "IN" * 3000, "output": "OUT" * 3000} for _ in range(6)]

    validator_prompt = build_validator_prompt(huge_desc, huge_constraints, public_tests, "")
    checker_prompt = build_checker_prompt(huge_desc, huge_constraints, public_tests, "")
    solver_prompt = build_solver_prompt(huge_desc, huge_constraints, public_tests, "T" * 12000, "F" * 6000, attempt=2)

    assert "[TRUNCATED" in validator_prompt
    assert "[TRUNCATED" in checker_prompt
    assert "[TRUNCATED" in solver_prompt


def test_analyze_compilation_errors_retries_with_compact_prompt_on_prompt_too_long():
    class FakeLLM:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                raise PromptTooLongError("prompt is too long: maximum context length")
            return "fixed"

    llm = FakeLLM()
    result = _analyze_compilation_errors(
        llm,
        "int main() {\n" + ("x++;\\n" * 10000) + "}\n",
        ["E" * 5000],
    )

    assert result["analysis"] == "fixed"
    assert len(llm.prompts) == 2
    assert "[TRUNCATED" in llm.prompts[1]


def test_generate_tests_generator_retries_with_compact_prompt_on_prompt_too_long():
    class FakeLLM:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                raise PromptTooLongError("prompt is too long: maximum context length")
            return "{\"generator_cpp\":\"int main(){return 0;}\"}"

    llm = FakeLLM()
    result = _generate_with_compact_retry(
        llm,
        build_generator_prompt,
        "P" * 20000,
        {"payload": "C" * 8000},
        [{"input": "I" * 5000, "output": "O" * 5000} for _ in range(6)],
        "F" * 4000,
        memory_advice="A" * 4000,
    )

    assert "generator_cpp" in result
    assert len(llm.prompts) == 2
    assert "[TRUNCATED" in llm.prompts[1]


def test_generate_tests_solver_retries_with_compact_prompt_on_prompt_too_long():
    class FakeLLM:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, **kwargs):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                raise PromptTooLongError("prompt is too long: maximum context length")
            return "{\"template_name\":\"x\",\"solver_cpp\":\"int main(){return 0;}\"}"

    llm = FakeLLM()
    result = _generate_with_compact_retry(
        llm,
        build_solver_prompt,
        "P" * 20000,
        {"payload": "C" * 8000},
        [{"input": "I" * 5000, "output": "O" * 5000} for _ in range(6)],
        "T" * 12000,
        "F" * 6000,
        attempt=2,
    )

    assert "solver_cpp" in result
    assert len(llm.prompts) == 2
    assert "[TRUNCATED" in llm.prompts[1]


def test_compute_certification_ratio_uses_actual_target_count():
    assert _compute_certification_ratio(certified_count=50, target_count=50) == 1.0
    assert _compute_certification_ratio(certified_count=2, target_count=50) == 0.04
    assert _compute_certification_ratio(certified_count=0, target_count=50) == 0.0


def test_resolve_selected_family_id_prefers_solver_declared_family():
    plan = OraclePlan(
        trainability_class="exact_single_answer",
        primary_family_id="oracle.enumeration.n_nested_loops",
        fallback_family_id="oracle.dp.topdown",
        route=OracleRoute.EXACT_SINGLE_ANSWER,
        acceptance_mode="safe",
        prompt_payloads=[],
    )
    solver_data = {"selected_family_id": "oracle.dp.topdown"}

    assert _resolve_selected_family_id(solver_data, plan) == "oracle.dp.topdown"


def test_resolve_selected_family_id_falls_back_to_primary_on_invalid_value():
    plan = OraclePlan(
        trainability_class="exact_single_answer",
        primary_family_id="oracle.enumeration.n_nested_loops",
        fallback_family_id="oracle.dp.topdown",
        route=OracleRoute.EXACT_SINGLE_ANSWER,
        acceptance_mode="safe",
        prompt_payloads=[],
    )
    solver_data = {"selected_family_id": "oracle.graph.all_paths"}

    assert _resolve_selected_family_id(solver_data, plan) == "oracle.enumeration.n_nested_loops"
