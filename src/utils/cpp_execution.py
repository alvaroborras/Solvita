"""
Shared utilities for C++ execution, compilation, and checking.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Union


def _detect_compiler() -> Optional[str]:
    """Return a usable C++ compiler binary path, if available."""
    for candidate in ("g++", "clang++"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def sanitize_cpp(code: str) -> str:
    """Strip markdown code blocks from LLM output."""
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()
    return code


def compile_cpp(
    source_path: Path, 
    exe_path: Path, 
    include_testlib: bool = False, 
    timeout: int = 30
) -> Tuple[bool, str]:
    """
    Compile C++ source code to executable.
    
    Args:
        source_path: Path to .cpp source file
        exe_path: Path where executable should be saved
        include_testlib: Whether to include current directory in include path (for testlib.h)
        timeout: Compilation timeout in seconds
        
    Returns:
        (success, output_log)
    """
    compiler = _detect_compiler()
    if not compiler:
        return False, "No C++ compiler found (tried g++ and clang++)"

    cmd = [compiler, "-std=c++17", "-O2"]
    if include_testlib:
        # Assuming testlib.h is in same dir as source or current working dir
        # -I. adds CWD to include path
        # Also add parent dir of source_path if needed
        cmd.append("-I.")
        if source_path.parent != Path("."):
            cmd.append(f"-I{source_path.parent}")
            
    cmd.extend([str(source_path), "-o", str(exe_path)])
    
    try:
        # Check for CCACHE_DISABLE usage from environment (set in benchmark/test scripts)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Compilation timed out after {timeout}s"
        
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output


def run_program(
    exe_path: Path, 
    input_text: Optional[str] = None, 
    args: Optional[List[str]] = None, 
    timeout: int = 2
) -> Tuple[int, str, str]:
    """
    Run an executable with stdin input or arguments.
    
    Returns:
        (return_code, stdout, stderr)
    """
    cmd = [str(exe_path)]
    if args:
        cmd.extend(args)
        
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def run_checker(
    checker_exe: Path, 
    input_path: Path, 
    output_path: Path, 
    answer_path: Path, 
    timeout: int = 2
) -> Tuple[bool, str]:
    """
    Run a Testlib checker.
    Usage: checker <input_file> <output_file> <answer_file>
    
    Returns:
        (is_correct, message)
    """
    ret, out, err = run_program(
        checker_exe,
        args=[str(input_path), str(output_path), str(answer_path)],
        timeout=timeout,
    )
    
    # Testlib checkers usually return 0 for OK, 1 for WA, 2 for PE, 3 for Fail
    # Output is usually to stderr (xml or text). Standard text is in stderr.
    if ret == 0:
        return True, err  # err contains "ok ..." message
    else:
        return False, err
