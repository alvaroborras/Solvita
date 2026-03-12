import pytest
from src.utils.python_execution import run_python

def test_run_python_success():
    """Test that safe python code runs and returns the correct output."""
    code = """
import math
import itertools
from collections import Counter

print(math.comb(10, 5))
print(Counter(['a', 'a', 'b'])['a'])
"""
    ret, out, err = run_python(code)
    assert ret == 0, f"Error: {err}"
    assert "252" in out
    assert "2" in out


def test_run_python_banned_import():
    """Test that banned imports are blocked by AST."""
    code = """
import os
os.system('echo "hacked"')
"""
    ret, out, err = run_python(code)
    assert ret == -1
    assert "SECURITY/SYNTAX ERROR" in err
    assert "strictly forbidden" in err


def test_run_python_banned_builtin():
    """Test that banned builtins like open are blocked by AST."""
    code = """
f = open('test.txt', 'w')
f.write('hacked')
f.close()
"""
    ret, out, err = run_python(code)
    assert ret == -1
    assert "strictly forbidden in sandbox" in err


def test_run_python_timeout():
    """Test that infinite loops are killed by timeout."""
    code = """
while True:
    pass
"""
    # Override limits for faster test
    from src.utils.cpp_execution import ExecutionLimits
    fast_limit = ExecutionLimits(
        wall_seconds=1, 
        cpu_seconds=1, 
        memory_bytes=256*1024*1024, 
        fsize_bytes=1024*1024,
        nproc=1,
        nofile=50
    )
    ret, out, err = run_python(code, limits=fast_limit)
    assert ret == 124
    assert "Time Limit Exceeded" in err

def test_run_python_banned_import_from():
    """Test that 'from module import ...' is blocked."""
    code = "from os import path"
    ret, out, err = run_python(code)
    assert ret == -1
    assert "strictly forbidden" in err

def test_run_python_markdown_stripping():
    """Test that markdown code fences are properly stripped."""
    code = "```python\nprint(42)\n```"
    ret, out, err = run_python(code)
    assert ret == 0
    assert "42" in out

def test_run_python_syntax_error():
    """Test what happens when the ast parse fails."""
    code = "def foo(::"
    ret, out, err = run_python(code)
    assert ret == -1
    assert "Syntax Error" in err

def test_run_python_framework_error(monkeypatch):
    """Test subprocess throwing an unexpected error."""
    import subprocess
    def mock_run(*args, **kwargs):
        raise OSError("Mock framework crash")
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    ret, out, err = run_python("print(1)")
    assert ret == -1
    assert "Execution Framework Error" in err
    assert "Mock framework crash" in err
