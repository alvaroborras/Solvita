"""
Shared utilities for C++ execution, compilation, and checking with sandboxing.
"""

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union, Callable

# Resource limiting (Linux only)
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False


@dataclass
class ExecutionLimits:
    """Resource limits for compilation and execution."""
    cpu_seconds: Optional[int] = None  # CPU time limit (RLIMIT_CPU)
    wall_seconds: Optional[int] = None  # Wall clock timeout (subprocess.run timeout)
    memory_bytes: Optional[int] = None  # Address space limit (RLIMIT_AS)
    fsize_bytes: Optional[int] = None  # Maximum file size (RLIMIT_FSIZE)
    nproc: Optional[int] = None  # Maximum number of processes (RLIMIT_NPROC)
    nofile: Optional[int] = None  # Maximum number of open files (RLIMIT_NOFILE)
    
    @staticmethod
    def default_compile() -> "ExecutionLimits":
        """Default limits for compilation."""
        return ExecutionLimits(
            cpu_seconds=30,
            wall_seconds=35,
            memory_bytes=2 * 1024 * 1024 * 1024,  # 2GB
            fsize_bytes=50 * 1024 * 1024,  # 50MB
            nproc=None,  # Do not limit: g++ needs to fork cc1plus; user-level RLIMIT_NPROC
                         # would block compilation if the server already has many processes.
            nofile=100,
        )
    
    @staticmethod
    def default_run() -> "ExecutionLimits":
        """Default limits for program execution."""
        return ExecutionLimits(
            cpu_seconds=2,
            wall_seconds=3,
            memory_bytes=512 * 1024 * 1024,  # 512MB
            fsize_bytes=10 * 1024 * 1024,  # 10MB
            nproc=1,
            nofile=50,
        )
    
    @staticmethod
    def diagnostic_compile() -> "ExecutionLimits":
        """Limits for diagnostic compilation with sanitizers (slower)."""
        return ExecutionLimits(
            cpu_seconds=60,
            wall_seconds=70,
            memory_bytes=4 * 1024 * 1024 * 1024,  # 4GB (sanitizers need more)
            fsize_bytes=100 * 1024 * 1024,  # 100MB
            nproc=None,  # Same reason as default_compile: don't limit process count.
            nofile=100,
        )

    @staticmethod
    def hacker_compile() -> "ExecutionLimits":
        """Strict limits for compiling hacker-generated C++ code."""
        return ExecutionLimits(
            cpu_seconds=10,
            wall_seconds=12,
            memory_bytes=2 * 1024 * 1024 * 1024,  # 2GB
            fsize_bytes=50 * 1024 * 1024,  # 50MB
            nproc=None,
            nofile=100,
        )

    @staticmethod
    def hacker_run() -> "ExecutionLimits":
        """Strict limits for running hacker-generated C++ code (Fuzzer/Generator)."""
        return ExecutionLimits(
            cpu_seconds=5,
            wall_seconds=6,
            memory_bytes=512 * 1024 * 1024,  # 512MB
            fsize_bytes=10 * 1024 * 1024,    # 10MB
            nproc=1,
            nofile=50,
        )


def _make_run_kwargs(limits: ExecutionLimits, work_dir: Optional[Path] = None, **base_kwargs) -> dict:
    """
    Build subprocess.run kwargs with platform-appropriate settings.
    
    On Unix/Linux: Uses preexec_fn for resource limits
    On Windows: Returns base_kwargs without preexec_fn (not supported)
    """
    kwargs = dict(base_kwargs)
    
    # Only use preexec_fn on Unix/Linux platforms
    if sys.platform != "win32" and HAS_RESOURCE:
        kwargs["preexec_fn"] = _make_preexec_fn(limits, work_dir=work_dir)
    elif work_dir:
        # On Windows, change directory using cwd parameter instead
        kwargs["cwd"] = str(work_dir)
    
    return kwargs


def _make_preexec_fn(limits: ExecutionLimits, work_dir: Optional[Path] = None) -> Callable:
    """
    Create a preexec_fn for subprocess that sets resource limits.
    
    Only works on Linux/Unix. Returns a no-op on Windows.
    """
    if not HAS_RESOURCE or sys.platform == "win32":
        # No resource limiting on Windows
        def noop_preexec():
            if work_dir:
                os.chdir(work_dir)
        return noop_preexec
    
    def preexec():
        """Set resource limits before executing the subprocess."""
        # Change to work directory first if specified
        if work_dir:
            os.chdir(work_dir)
        
        # CPU time limit (seconds of CPU time)
        cpu_sec = limits.cpu_seconds
        if cpu_sec is not None:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_sec, cpu_sec))
        
        # Address space limit (memory)
        mem_bytes = limits.memory_bytes
        if mem_bytes is not None:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        
        # File size limit
        fsize = limits.fsize_bytes
        if fsize is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        
        # Process count limit
        nproc = limits.nproc
        if nproc is not None:
            resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
        
        # Open files limit
        nofile = limits.nofile
        if nofile is not None:
            resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
    
    return preexec


def _minimal_env() -> dict:
    """Return a minimal environment for subprocess execution."""
    # Keep essential env vars only
    minimal = {}
    for key in ["PATH", "HOME", "TMPDIR", "TMP", "TEMP"]:
        if key in os.environ:
            minimal[key] = os.environ[key]
    
    # Set LC_ALL to avoid locale issues
    minimal["LC_ALL"] = "C.UTF-8"
    return minimal


def _detect_compiler() -> Optional[str]:
    """Return a usable C++ compiler binary path, if available."""
    for candidate in ("g++", "clang++"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def sanitize_cpp(code: str) -> str:
    """
    Strip markdown code blocks from LLM output.
    Also performs security scanning to reject malicious OS-level calls (T1.2).
    Raises ValueError if malicious code is detected.
    """
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines and lines[0].startswith("```"):
            lines.pop(0)
        if lines and lines[-1].strip() == "```":
            lines.pop()
        code = "\n".join(lines).strip()
        
    # Security Scan (T1.2)
    dangerous_patterns = [
        r"#include\s*<unistd\.h>",
        r"#include\s*<sys/socket\.h>",
        r"#include\s*<windows\.h>",
        r"\bsystem\s*\(",
        r"\bfork\s*\(",
        r"\bexec[a-z]*\s*\(",
        r"\bpopen\s*\(",
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            raise ValueError(f"SECURITY_VIOLATION: Detect banned pattern '{pattern}' in C++ source.")
            
    return code


def compile_cpp(
    source_path: Path, 
    exe_path: Path, 
    include_testlib: bool = False, 
    limits: Optional[ExecutionLimits] = None,
    diagnostic: bool = False,
) -> Tuple[bool, str]:
    """
    Compile C++ source code to executable with resource limits.
    
    Args:
        source_path: Path to .cpp source file
        exe_path: Path where executable should be saved
        include_testlib: Whether to include current directory in include path (for testlib.h)
        limits: Resource limits (defaults to ExecutionLimits.default_compile())
        diagnostic: If True, compile with sanitizers for debugging
        
    Returns:
        (success, output_log)
    """
    compiler = _detect_compiler()
    if not compiler:
        return False, "No C++ compiler found (tried g++ and clang++)"

    source_abs = source_path.resolve()
    exe_abs = exe_path.resolve()

    if not source_abs.exists():
        return False, f"Source file not found: {source_abs}"

    try:
        source_content = source_abs.read_text(encoding="utf-8")
        sanitize_cpp(source_content)
    except ValueError as e:
        return False, f"COMPILE_ERROR: {str(e)}"

    if limits is None:
        limits = ExecutionLimits.diagnostic_compile() if diagnostic else ExecutionLimits.default_compile()
    
    # Build compiler command
    cmd = [compiler, "-std=c++17"]
    
    if diagnostic:
        # Diagnostic mode: sanitizers, debug info, less optimization
        cmd.extend(["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"])
    else:
        # Normal mode: optimized
        cmd.append("-O2")
    
    if include_testlib:
        cmd.extend(["-include", "cstdint"])
        include_dirs = [source_abs.parent]

        for parent in source_abs.parents:
            testlib_candidate = parent / "testlib.h"
            if testlib_candidate.exists():
                include_dirs.append(parent)
                break

        seen_dirs = set()
        for inc_dir in include_dirs:
            inc_key = str(inc_dir)
            if inc_key not in seen_dirs:
                cmd.append(f"-I{inc_dir}")
                seen_dirs.add(inc_key)
    
    cmd.extend([str(source_abs), "-o", str(exe_abs)])
    
    try:
        # Ensure parent dir exists
        exe_abs.parent.mkdir(parents=True, exist_ok=True)
        
        # Run with resource limits
        run_kwargs = _make_run_kwargs(
            limits,
            work_dir=source_abs.parent,
            capture_output=True,
            text=True,
            timeout=limits.wall_seconds,
            env=_minimal_env(),
        )
        result = subprocess.run(cmd, **run_kwargs)
    except subprocess.TimeoutExpired:
        return False, f"Compilation timed out after {limits.wall_seconds}s"
    except Exception as e:
        return False, f"Compilation failed: {e}"
        
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output


def _truncate_output(text: str, max_chars: int = 100000) -> str:
    """Truncate text to max_chars, keeping head and tail if exceeded."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + f"\n... [TRUNCATED {len(text) - max_chars} CHARS] ...\n" + text[-half:]


def cleanup_tempdir(
    path: Path,
    windows_retry_attempts: int = 5,
    windows_retry_delay: float = 0.1,
    windows_ignore_permission_errors: bool = False,
) -> None:
    """
    Remove a temporary directory.

    On Windows only, retry PermissionError a few times because freshly executed
    .exe files may remain locked briefly by the OS or antivirus scanners.
    """
    if not path.exists():
        return

    if sys.platform != "win32":
        shutil.rmtree(path)
        return

    attempts = max(1, windows_retry_attempts)
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt < attempts - 1:
                time.sleep(windows_retry_delay)
                continue
            if windows_ignore_permission_errors:
                return
            raise


def run_program(
    exe_path: Path, 
    input_text: Optional[str] = None, 
    args: Optional[List[str]] = None, 
    limits: Optional[ExecutionLimits] = None,
    truncate_output: bool = True,
) -> Tuple[int, str, str]:
    """
    Run an executable with stdin input or arguments, with resource limits.
    
    Args:
        exe_path: Path to executable
        input_text: Input to pass via stdin
        args: Command-line arguments
        limits: Resource limits (defaults to ExecutionLimits.default_run())
        truncate_output: Whether to truncate stdout/stderr for logging safety
    
    Returns:
        (return_code, stdout, stderr)
    """
    if limits is None:
        limits = ExecutionLimits.default_run()

    # Resolve to absolute path to avoid chdir conflicts in preexec_fn
    exe_path = exe_path.resolve()

    cmd = [str(exe_path)]
    if args:
        cmd.extend(args)
    
    try:
        # Run in parent directory of executable with minimal env
        work_dir = exe_path.parent
        
        run_kwargs = _make_run_kwargs(
            limits,
            work_dir=work_dir,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=limits.wall_seconds,
            env=_minimal_env(),
        )
        result = subprocess.run(cmd, **run_kwargs)
        
        if truncate_output:
            # Physical truncation to prevent log bloat in human-facing logs.
            stdout = _truncate_output(result.stdout)
            stderr = _truncate_output(result.stderr)
        else:
            stdout = result.stdout
            stderr = result.stderr
        
        return result.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Time Limit Exceeded"
    except Exception as e:
        return -1, "", str(e)


def run_checker(
    checker_exe: Path, 
    input_path: Path, 
    output_path: Path, 
    answer_path: Path, 
    limits: Optional[ExecutionLimits] = None,
) -> Tuple[bool, str]:
    """
    Run a Testlib checker with resource limits.
    Usage: checker <input_file> <output_file> <answer_file>
    
    Args:
        checker_exe: Path to checker executable
        input_path: Path to input file
        output_path: Path to output file
        answer_path: Path to answer file
        limits: Resource limits (defaults to ExecutionLimits.default_run())
    
    Returns:
        (is_correct, message)
    """
    ret, out, err = run_program(
        checker_exe,
        args=[str(input_path.resolve()), str(output_path.resolve()), str(answer_path.resolve())],
        limits=limits,
    )
    
    # Testlib checkers usually return 0 for OK, 1 for WA, 2 for PE, 3 for Fail
    # Output is usually to stderr (xml or text). Standard text is in stderr.
    if ret == 0:
        return True, err  # err contains "ok ..." message
    else:
        return False, err
