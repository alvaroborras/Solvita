import json
import pytest
from unittest.mock import MagicMock
from src.nodes.code_analyst import parse_code_analyst_response, execute_tool, run_code_analyst

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
    
    # Needs 5 calls for 5 failed rounds
    assert mock_llm.generate.call_count == 5
    # Should return fallback report
    assert report["bug_class"] == "unknown"
    assert report["suggested_route"] == "semantic"

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
