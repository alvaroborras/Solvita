import os
import tempfile
import pytest
from pathlib import Path
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits, cleanup_tempdir

def test_hacker_compile_success():
    """Test that a valid C++ file compiles successfully with hacker limits."""
    code = """
#include <iostream>
int main() {
    std::cout << "Hello Hackers!" << std::endl;
    return 0;
}
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "test.cpp"
        exe = Path(tmpdir) / "test.exe"
        src.write_text(code)
        
        success, out = compile_cpp(src, exe, limits=ExecutionLimits.hacker_compile())
        assert success is True, f"Compilation failed: {out}"
        assert exe.exists()

def test_hacker_run_success():
    """Test that a compiled execution runs and respects the time limit."""
    code = """
#include <iostream>
int main() {
    std::cout << "Data" << std::endl;
    return 0;
}
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "test.cpp"
        exe = Path(tmpdir) / "test.exe"
        src.write_text(code)
        
        compile_cpp(src, exe, limits=ExecutionLimits.hacker_compile())
        
        ret, stdout, stderr = run_program(exe, limits=ExecutionLimits.hacker_run())
        assert ret == 0
        assert "Data" in stdout

def test_hacker_run_timeout():
    """Test that an infinite loop is cut off by the timeout limit."""
    code = """
#include <iostream>
int main() {
    while(true) {}
    return 0;
}
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "test.cpp"
        exe = Path(tmpdir) / "test.exe"
        src.write_text(code)
        
        compile_cpp(src, exe, limits=ExecutionLimits.hacker_compile())
        
        # We override wall_seconds to 1s to make the test run faster,
        # but keep it structurally identical.
        fast_limit = ExecutionLimits.hacker_run()
        fast_limit.wall_seconds = 1
        fast_limit.cpu_seconds = 1
        
        ret, stdout, stderr = run_program(exe, limits=fast_limit)
        assert ret == 124
        assert "Time Limit Exceeded" in stderr


def test_cleanup_tempdir_retries_permission_error_on_windows(monkeypatch, tmp_path):
    target = tmp_path / "locked"
    target.mkdir()
    calls = {"n": 0}
    sleeps = []

    def fake_rmtree(path):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access denied", str(path))

    monkeypatch.setattr("src.utils.cpp_execution.shutil.rmtree", fake_rmtree)
    monkeypatch.setattr("src.utils.cpp_execution.time.sleep", lambda delay: sleeps.append(delay))
    monkeypatch.setattr("src.utils.cpp_execution.sys.platform", "win32")

    cleanup_tempdir(target, windows_retry_attempts=3, windows_retry_delay=0.01)

    assert calls["n"] == 3
    assert sleeps == [0.01, 0.01]


def test_cleanup_tempdir_can_ignore_windows_permission_error(monkeypatch, tmp_path):
    target = tmp_path / "locked"
    target.mkdir()
    calls = {"n": 0}

    def fake_rmtree(path):
        calls["n"] += 1
        raise PermissionError(5, "Access denied", str(path))

    monkeypatch.setattr("src.utils.cpp_execution.shutil.rmtree", fake_rmtree)
    monkeypatch.setattr("src.utils.cpp_execution.time.sleep", lambda delay: None)
    monkeypatch.setattr("src.utils.cpp_execution.sys.platform", "win32")

    cleanup_tempdir(
        target,
        windows_retry_attempts=2,
        windows_retry_delay=0.01,
        windows_ignore_permission_errors=True,
    )

    assert calls["n"] == 2


def test_cleanup_tempdir_does_not_apply_windows_ignore_logic_on_linux(monkeypatch, tmp_path):
    target = tmp_path / "locked"
    target.mkdir()
    calls = {"n": 0}

    def fake_rmtree(path):
        calls["n"] += 1
        raise PermissionError(5, "Access denied", str(path))

    monkeypatch.setattr("src.utils.cpp_execution.shutil.rmtree", fake_rmtree)
    monkeypatch.setattr("src.utils.cpp_execution.sys.platform", "linux")

    with pytest.raises(PermissionError):
        cleanup_tempdir(
            target,
            windows_retry_attempts=3,
            windows_retry_delay=0.01,
            windows_ignore_permission_errors=True,
        )

    assert calls["n"] == 1
