import pytest
from pathlib import Path
from src.nodes.generate_tests import format_solver_feedback, build_solver_prompt

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
