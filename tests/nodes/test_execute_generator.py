import pytest
from unittest.mock import MagicMock
from src.nodes.cascading_router import execute_generator_and_validate

def test_execute_compile_fail(monkeypatch, tmp_path):
    """Test that compilation failure returns (False, "", error_message)."""
    def mock_compile(*args, **kwargs):
        return False, "error: expected ; before }"
    monkeypatch.setattr("src.nodes.cascading_router.compile_cpp", mock_compile)
    
    ok, result, err = execute_generator_and_validate("int main{ }", None, {})
    
    assert ok is False
    assert "Compilation Failed" in err
    assert "expected ; before" in err

def test_execute_generator_empty_output(monkeypatch, tmp_path):
    """Test that empty generator output is reported as failure."""
    monkeypatch.setattr("src.nodes.cascading_router.compile_cpp", lambda *a, **k: (True, ""))
    monkeypatch.setattr("src.nodes.cascading_router.run_program", lambda *a, **k: (0, "", ""))

    ok, result, err = execute_generator_and_validate("int main(){}", None, {})
    
    assert ok is False
    assert "empty output" in err

def test_execute_generator_runtime_error(monkeypatch):
    """Test that a non-zero returncode from generator is reported correctly."""
    monkeypatch.setattr("src.nodes.cascading_router.compile_cpp", lambda *a, **k: (True, ""))
    monkeypatch.setattr("src.nodes.cascading_router.run_program", lambda *a, **k: (1, "", "segfault"))

    ok, result, err = execute_generator_and_validate("int main(){}", None, {})
    
    assert ok is False
    assert "execution failed" in err

def test_execute_generator_success_no_validator(monkeypatch):
    """Test that if no validator, a non-empty output is returned as success."""
    monkeypatch.setattr("src.nodes.cascading_router.compile_cpp", lambda *a, **k: (True, ""))
    monkeypatch.setattr("src.nodes.cascading_router.run_program", lambda *a, **k: (0, "3\n1 2 3\n", ""))

    ok, result, err = execute_generator_and_validate("int main(){}", None, {})
    
    assert ok is True
    assert "3\n1 2 3\n" in result
    assert err == ""

def test_execute_generator_validator_rejects(monkeypatch, tmp_path):
    """Test that validator rejection causes (False, ...) return."""
    monkeypatch.setattr("src.nodes.cascading_router.compile_cpp", lambda *a, **k: (True, ""))
    monkeypatch.setattr("src.nodes.cascading_router.run_program", lambda *a, **k: (0, "bad_input\n", ""))

    # Create a fake validator exe that always fails
    fake_validator = tmp_path / "val.exe"
    fake_validator.write_bytes(b"")
    
    def mock_run_validator(exe, input_text, limits):
        return 1, "", "invalid N > max_N"
    
    monkeypatch.setattr("src.nodes.cascading_router.run_program", 
        lambda exe, **kwargs: (1, "", "invalid N > max_N") if str(exe).endswith("val.exe") else (0, "1\n", "")
    )
    
    ok, result, err = execute_generator_and_validate("int main(){}", fake_validator, {})
    
    assert ok is False
    assert "Validation Failed" in err
