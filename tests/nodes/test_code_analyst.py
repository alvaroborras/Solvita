import json
import pytest
from unittest.mock import MagicMock
from src.nodes.code_analyst import parse_code_analyst_response, execute_tool, run_code_analyst, build_analyst_prompt
from src.llm.unified_client import PromptTooLongError
from src.nodes import code_analyst

def test_parse_analyst_tool_call():
    """Test parsing a valid tool call."""
    resp = '''```json
{
    "tool": "run_python",
    "parameters": {"script_code": "print(1)"}
}
```'''
    res_type, parsed = parse_code_analyst_response(resp)
    assert res_type == "tool_call"
    assert parsed["tool"] == "run_python"

def test_parse_analyst_final_report():
    """Test parsing a valid final report."""
    resp = json.dumps({
        "bug_class": "overflow",
        "confidence": "high",
        "evidence": ["test"],
        "suggested_route": "semantic",
        "input_hypothesis": ["test_n"]
    })
    res_type, parsed = parse_code_analyst_response(resp)
    assert res_type == "final_report"
    assert parsed["bug_class"] == "overflow"

def test_parse_analyst_invalid_tool():
    """Test schema guard rejects invalid tool name."""
    resp = json.dumps({
        "tool": "run_bash",
        "parameters": {"script": "rm -rf"}
    })
    res_type, parsed = parse_code_analyst_response(resp)
    assert res_type == "error"
    assert "Forbidden or unknown tool 'run_bash'" in parsed["message"]

def test_parse_analyst_missing_keys():
    """Test schema guard rejects incomplete final reports."""
    resp = json.dumps({
        "bug_class": "overflow",
        "suggested_route": "semantic"
        # missing confidence, evidence, input_hypothesis
    })
    res_type, parsed = parse_code_analyst_response(resp)
    assert res_type == "error"
    assert "missing required keys" in parsed["message"]

def test_parse_analyst_invalid_enum():
    """Test schema guard rejects invalid enum values."""
    base_report = {
        "bug_class": "overflow",
        "confidence": "high",
        "evidence": ["e"],
        "suggested_route": "semantic",
        "input_hypothesis": ["i"]
    }
    
    # invalid bug_class
    d1 = dict(base_report); d1["bug_class"] = "not_real"
    res_type, parsed = parse_code_analyst_response(json.dumps(d1))
    assert res_type == "error" and "Invalid bug_class" in parsed["message"]
    
    # invalid confidence
    d2 = dict(base_report); d2["confidence"] = "super_high"
    res_type, parsed = parse_code_analyst_response(json.dumps(d2))
    assert res_type == "error" and "Invalid confidence" in parsed["message"]
    
    # invalid route
    d3 = dict(base_report); d3["suggested_route"] = "random"
    res_type, parsed = parse_code_analyst_response(json.dumps(d3))
    assert res_type == "error" and "Invalid suggested_route" in parsed["message"]
    
    # invalid list type
    d4 = dict(base_report); d4["evidence"] = "not a list"
    res_type, parsed = parse_code_analyst_response(json.dumps(d4))
    assert res_type == "error" and "must be lists" in parsed["message"]

def test_parse_analyst_unrecognized_json():
    """Test schema guard rejects generic json object."""
    resp = json.dumps({"greeting": "hello", "info": "not a report"})
    res_type, parsed = parse_code_analyst_response(resp)
    assert res_type == "error"
    assert "Unrecognized JSON structure" in parsed["message"]


def test_parse_analyst_extracts_fenced_json_after_preface():
    resp = """I checked it carefully.

```json
{
  "bug_class": "overflow",
  "confidence": "high",
  "evidence": ["saw a large accumulation"],
  "suggested_route": "semantic",
  "input_hypothesis": ["large_n"]
}
```"""
    res_type, parsed = parse_code_analyst_response(resp)
    assert res_type == "final_report"
    assert parsed["bug_class"] == "overflow"

def test_execute_tool_unknown():
    out = execute_tool("run_magic", {})
    assert "not implemented" in out

def test_execute_tool_python_missing_code():
    out = execute_tool("run_python", {})
    assert "Missing 'script_code'" in out

def test_execute_tool_python_timeout(monkeypatch):
    # Mocking run_python to return a timeout signal
    def mock_run_python(*args, **kwargs):
        return 124, "", "Time Limit Exceeded"
    monkeypatch.setattr("src.nodes.code_analyst.run_python", mock_run_python)
    out = execute_tool("run_python", {"script_code": "while True: pass"})
    assert "Timeout!" in out

def test_execute_tool_python_fail(monkeypatch):
    def mock_run_python(*args, **kwargs):
        return 1, "", "SyntaxError"
    monkeypatch.setattr("src.nodes.code_analyst.run_python", mock_run_python)
    out = execute_tool("run_python", {"script_code": "print(1"})
    assert "Execution failed" in out

def test_execute_tool_cpp_missing_code():
    out = execute_tool("run_cpp", {})
    assert "Missing 'cpp_code'" in out

def test_execute_tool_cpp_compile_fail(monkeypatch):
    from src.utils.cpp_execution import ExecutionLimits
    def mock_compile(*args, **kwargs):
        return False, "compile error"
    monkeypatch.setattr("src.nodes.code_analyst.compile_cpp", mock_compile)
    out = execute_tool("run_cpp", {"cpp_code": "int main"})
    assert "Compilation failed" in out

def test_execute_tool_cpp_run_timeout(monkeypatch):
    def mock_compile(*args, **kwargs): return True, ""
    def mock_run(*args, **kwargs): return 124, "", "TLE"
    monkeypatch.setattr("src.nodes.code_analyst.compile_cpp", mock_compile)
    monkeypatch.setattr("src.nodes.code_analyst.run_program", mock_run)
    out = execute_tool("run_cpp", {"cpp_code": "int main() {while(true){}}"})
    assert "Timeout!" in out

def test_execute_tool_cpp_run_fail(monkeypatch):
    def mock_compile(*args, **kwargs): return True, ""
    def mock_run(*args, **kwargs): return 139, "", "Segfault"
    monkeypatch.setattr("src.nodes.code_analyst.compile_cpp", mock_compile)
    monkeypatch.setattr("src.nodes.code_analyst.run_program", mock_run)
    out = execute_tool("run_cpp", {"cpp_code": "int main() {return 139;}"})
    assert "Runtime Error" in out

def test_execute_tool_cpp_success(monkeypatch):
    def mock_compile(*args, **kwargs): return True, ""
    def mock_run(*args, **kwargs): return 0, "cpp_success", ""
    monkeypatch.setattr("src.nodes.code_analyst.compile_cpp", mock_compile)
    monkeypatch.setattr("src.nodes.code_analyst.run_program", mock_run)
    out = execute_tool("run_cpp", {"cpp_code": "int main() {}"})
    assert "Execution successful" in out
    assert "cpp_success" in out

def test_run_code_analyst_loop():
    """Test the Analyst Controller respects the 5-round limit and falls back."""
    mock_llm = MagicMock()
    # Always return invalid JSON
    mock_llm.generate.return_value = "This is not JSON at all."
    
    state = {
        "problem": {"description": "test", "constraints": {}},
        "solution": {"code": "int main() {}"}
    }
    
    report = run_code_analyst(state, mock_llm, max_rounds=5)
    
    # Each failed round now includes one repair attempt.
    assert mock_llm.generate.call_count == 10
    # Should return fallback report
    assert report["bug_class"] == "unknown"
    assert report["suggested_route"] == "semantic"


def test_run_code_analyst_prefers_system_prompt_channel():
    class DummyLLM:
        def generate(self, prompt, **kwargs):
            raise AssertionError("generate() should not be used when system prompt channel is available")

        def generate_with_system(self, system, user, **kwargs):
            assert "Return ONLY valid JSON" in system
            return json.dumps({
                "bug_class": "logic_branch",
                "confidence": "medium",
                "evidence": ["system prompt path"],
                "suggested_route": "semantic",
                "input_hypothesis": ["edge_case"],
            })

    state = {
        "problem": {"description": "test", "constraints": {}},
        "solution": {"code": "int main() {}"},
    }

    report = run_code_analyst(state, DummyLLM(), max_rounds=1)

    assert report["bug_class"] == "logic_branch"

def test_run_code_analyst_success():
    """Test Analyst successfully finishing after tool calls."""
    mock_llm = MagicMock()
    
    # 1st call: Tool Call
    # 2nd call: Final Report
    mock_llm.generate.side_effect = [
        json.dumps({
            "tool": "run_python",
            "parameters": {"script_code": "print('ToolWorks')"}
        }),
        json.dumps({
            "bug_class": "logic_branch",
            "confidence": "medium",
            "evidence": ["Works"],
            "suggested_route": "semantic",
            "input_hypothesis": ["Valid"]
        })
    ]
    
    state = {"problem": {}, "solution": {}}
    report = run_code_analyst(state, mock_llm)
    
    assert mock_llm.generate.call_count == 2
    assert report["bug_class"] == "logic_branch"


def test_run_code_analyst_repairs_invalid_json_without_consuming_extra_round():
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = [
        "I think this is probably a logic bug.",
        json.dumps({
            "bug_class": "logic_branch",
            "confidence": "medium",
            "evidence": ["Repair pass preserved the original conclusion."],
            "suggested_route": "semantic",
            "input_hypothesis": ["edge_case_branch"],
        }),
    ]

    state = {
        "problem": {"description": "test", "constraints": {}},
        "solution": {"code": "int main() {}"},
    }

    report = run_code_analyst(state, mock_llm, max_rounds=1)

    assert report["bug_class"] == "logic_branch"
    assert mock_llm.generate.call_count == 2
    repair_prompt = mock_llm.generate.call_args_list[1].args[0]
    assert "valid JSON" in repair_prompt
    assert "do not add any explanation" in repair_prompt.lower()


def test_run_code_analyst_repair_prompt_reuses_full_context():
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = [
        "I suspect an overflow but this is not json.",
        json.dumps({
            "bug_class": "overflow",
            "confidence": "medium",
            "evidence": ["large accumulation may overflow int"],
            "suggested_route": "semantic",
            "input_hypothesis": ["large_n"],
        }),
    ]

    state = {
        "problem": {
            "description": "Given N numbers, compute the sum.",
            "constraints": {"n": "1..1e5"},
        },
        "solution": {"code": "int main() { return 0; }"},
    }

    run_code_analyst(
        state,
        mock_llm,
        max_rounds=1,
        memory_advice="Prefer large accumulation edge cases.",
    )

    repair_prompt = mock_llm.generate.call_args_list[1].args[0]
    assert "Given N numbers, compute the sum." in repair_prompt
    assert '"n": "1..1e5"' in repair_prompt
    assert "int main() { return 0; }" in repair_prompt
    assert "Prefer large accumulation edge cases." in repair_prompt


def test_run_code_analyst_forces_tool_call_for_low_quality_report(monkeypatch):
    mock_llm = MagicMock()
    weak_report = json.dumps({
        "bug_class": "unknown",
        "confidence": "low",
        "evidence": ["Need more validation"],
        "suggested_route": "semantic",
        "input_hypothesis": ["large_n"],
    })
    tool_call = json.dumps({
        "tool": "run_python",
        "parameters": {"script_code": "print(42)"},
    })
    stronger_report = json.dumps({
        "bug_class": "overflow",
        "confidence": "medium",
        "evidence": ["Validated with a probe calculation"],
        "suggested_route": "semantic",
        "input_hypothesis": ["large_n accumulation"],
    })
    mock_llm.generate.side_effect = [weak_report, tool_call, stronger_report]

    monkeypatch.setattr("src.nodes.code_analyst.execute_tool", lambda tool_name, parameters: "Execution successful:\n42")

    state = {
        "problem": {
            "description": "Sum many numbers.",
            "constraints": {"n": "1..1e5"},
        },
        "solution": {"code": "int main() { return 0; }"},
    }

    report = run_code_analyst(state, mock_llm, max_rounds=1)

    assert report["bug_class"] == "overflow"
    assert mock_llm.generate.call_count == 3
    forced_prompt = mock_llm.generate.call_args_list[1].args[0]
    assert "must call exactly one tool" in forced_prompt.lower()
    assert "do not submit a final report yet" in forced_prompt.lower()


def test_run_code_analyst_allows_low_quality_report_after_tool_evidence(monkeypatch):
    mock_llm = MagicMock()
    tool_call = json.dumps({
        "tool": "run_python",
        "parameters": {"script_code": "print(42)"},
    })
    weak_report = json.dumps({
        "bug_class": "unknown",
        "confidence": "low",
        "evidence": ["Still inconclusive after verification"],
        "suggested_route": "semantic",
        "input_hypothesis": ["large_n"],
    })
    mock_llm.generate.side_effect = [tool_call, weak_report]

    monkeypatch.setattr("src.nodes.code_analyst.execute_tool", lambda tool_name, parameters: "Execution successful:\n42")

    state = {
        "problem": {"description": "test", "constraints": {}},
        "solution": {"code": "int main() {}"},
    }

    report = run_code_analyst(state, mock_llm, max_rounds=2)

    assert report["bug_class"] == "unknown"
    assert mock_llm.generate.call_count == 2


def test_build_analyst_prompt_includes_memory_advice():
    prompt = build_analyst_prompt(
        "problem",
        {"n": "1..10"},
        "int main() {}",
        [],
        memory_advice="Prefer edge cases with repeated prefixes.",
    )

    assert "HACKER STRATEGY ADVICE" in prompt
    assert "repeated prefixes" in prompt


def test_build_analyst_prompt_truncates_large_context():
    prompt = build_analyst_prompt(
        "P" * 20000,
        {"payload": "C" * 8000},
        "int main() {\n" + ("x++;\\n" * 10000) + "}\n",
        ["history " + ("H" * 5000) for _ in range(6)],
        memory_advice="Prefer repeated prefixes.",
    )

    assert "[TRUNCATED" in prompt
    assert len(prompt) < 45000


def test_run_code_analyst_retries_with_compact_prompt_on_prompt_too_long(monkeypatch):
    class FakeLLM:
        def __init__(self):
            self.calls = []

        def generate(self, prompt, **kwargs):
            self.calls.append(prompt)
            if len(self.calls) == 1:
                raise PromptTooLongError("prompt is too long: maximum context length")
            return """{
              "bug_class": "unknown",
              "confidence": "low",
              "evidence": ["fallback"],
              "suggested_route": "semantic",
              "input_hypothesis": ["large_n"]
            }"""

    llm = FakeLLM()
    state = {
        "problem": {"description": "P" * 20000, "constraints": {"payload": "C" * 8000}},
        "solution": {"code": "int main() {\n" + ("x++;\\n" * 10000) + "}\n"},
    }

    report = run_code_analyst(state, llm, max_rounds=1)

    assert report["bug_class"] == "unknown"
    assert len(llm.calls) == 3
    assert "[TRUNCATED" in llm.calls[1]


def test_build_analyst_prompt_trims_old_and_large_history():
    history = [
        "oldest entry should be dropped",
        "middle entry:\n" + ("x" * 12000),
        "recent entry should stay",
    ]

    prompt = build_analyst_prompt(
        "problem",
        {"n": "1..10"},
        "int main() {}",
        history,
    )

    assert "oldest entry should be dropped" not in prompt
    assert "recent entry should stay" in prompt
    assert len(prompt) < 10000


def test_run_code_analyst_forwards_compaction_kwargs(monkeypatch):
    observed = {}

    def fake_chat_with_history(llm, messages_history, prompt, **kwargs):
        observed["messages_history"] = list(messages_history)
        observed["prompt"] = prompt
        observed["system_content"] = kwargs.get("system_content")
        observed["compaction_context"] = kwargs.get("compaction_context")
        observed["compaction_config"] = kwargs.get("compaction_config")
        observed["temperature"] = kwargs.get("temperature")
        return (
            json.dumps({
                "bug_class": "logic_branch",
                "confidence": "medium",
                "evidence": ["forwarded through direct helper"],
                "suggested_route": "semantic",
                "input_hypothesis": ["edge_case"],
            }),
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "ok"},
            ],
            [
                {"role": "assistant", "content": "previous context"},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "ok"},
            ],
        )

    monkeypatch.setattr(code_analyst, "chat_with_history", fake_chat_with_history)

    state = {
        "current_phase": "HACK",
        "iteration": 2,
        "max_iterations": 5,
        "problem": {
            "description": "test problem",
            "constraints": {"n": "1..10"},
            "canonical": {"objective": "find a counterexample"},
        },
        "solution": {"code": "int main() {}"},
        "plan": {
            "memory_advice": "Prefer branching edge cases.",
            "skill_selection_skill_ids": ["skill.branch"],
        },
        "feedback": {"feedback": {"analysis": "prior failure", "failures": [{"kind": "wa"}]}},
        "execution_log": ["step1", "step2"],
        "config": {"message_compaction": {"enabled": True, "max_history_ratio": 0.5}},
    }
    history = [{"role": "assistant", "content": "previous context"}]

    report, new_messages = run_code_analyst(state, MagicMock(), max_rounds=1, messages_history=history)

    assert report["bug_class"] == "logic_branch"
    assert observed["messages_history"] == history
    assert "Return ONLY valid JSON" in observed["system_content"]
    assert observed["temperature"] == 0.0
    assert observed["compaction_context"]["node_name"] == "code_analyst"
    assert observed["compaction_context"]["current_objective"] == "find a counterexample"
    assert observed["compaction_context"]["skill_selection_skill_ids"] == ["skill.branch"]
    assert observed["compaction_config"] == state["config"]
    assert new_messages[-1]["role"] == "assistant"


def test_execute_tool_cpp_rejects_overlarge_probe_before_compile(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("compile_cpp should not run for overlarge probes")

    monkeypatch.setattr("src.nodes.code_analyst.compile_cpp", should_not_run)

    out = execute_tool("run_cpp", {"cpp_code": "int main(){}\n" + ("// filler\n" * 5000)})

    assert "too large" in out.lower()
