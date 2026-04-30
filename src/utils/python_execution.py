"""
Execution sandbox for Python scripts used by Code Analyst.
Ensures strict resource limits and denies dangerous imports/functions.
"""

import ast
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple

# Re-use ExecutionLimits and OS-level platform settings from cpp_execution
from src.utils.cpp_execution import ExecutionLimits, _make_run_kwargs, _minimal_env

class SecurityViolationError(ValueError):
    """Raised when Python code violates security policies."""
    pass

class PythonSandboxAnalyzer(ast.NodeVisitor):
    """
    AST visitor to check for banned imports and dangerous builtins.
    Allowed imports: math, itertools, collections.
    Disallowed calls: open, eval, exec, compile, __import__.
    """
    # Strict arithmetic and algorithmic whitelist (sys for stdin/stdout, random for input generation)
    ALLOWED_IMPORTS = {"math", "itertools", "collections", "bisect", "heapq", "sys", "random"}
    BANNED_BUILTIN_CALLS = {"open", "eval", "exec", "compile", "__import__"}

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_module = alias.name.split('.')[0]
            if base_module not in self.ALLOWED_IMPORTS:
                raise SecurityViolationError(f"Import of module '{base_module}' is strictly forbidden in sandbox.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_module = node.module.split('.')[0]
            if base_module not in self.ALLOWED_IMPORTS:
                raise SecurityViolationError(f"Import from module '{base_module}' is strictly forbidden in sandbox.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in self.BANNED_BUILTIN_CALLS:
                raise SecurityViolationError(f"Call to builtin '{node.func.id}' is strictly forbidden in sandbox.")
        self.generic_visit(node)


def sanitize_python(code: str) -> str:
    """
    Strips markdown formatting and statically analyzes the AST for security violations.
    """
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines and lines[0].startswith("```"):
            lines.pop(0)
        if lines and lines[-1].strip() == "```":
            lines.pop()
        code = "\n".join(lines).strip()

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Syntax Error in generated Python code: {e}")

    analyzer = PythonSandboxAnalyzer()
    analyzer.visit(tree)

    return code


def run_python(
    script_code: str,
    limits: Optional[ExecutionLimits] = None
) -> Tuple[int, str, str]:
    """
    Runs Python code in a restricted subprocess.
    
    Args:
        script_code: The Python script to execute.
        limits: Constraints for cpu, memory, file size, etc.
        
    Returns:
        (return_code, stdout, stderr)
    """
    # 1. Enforce strict static analysis first
    try:
        clean_code = sanitize_python(script_code)
    except Exception as e:
        return -1, "", f"SECURITY/SYNTAX ERROR: {str(e)}"

    # 2. Setup execution limits if not provided (5s timeout, 256MB memory)
    if limits is None:
        limits = ExecutionLimits(
            cpu_seconds=5,
            wall_seconds=6,
            memory_bytes=256 * 1024 * 1024,  # 256MB
            fsize_bytes=1024 * 1024,          # 1MB output restriction
            nproc=1,
            nofile=50,
        )

    # 3. Create a temporary file to run
    # Use delete=False because Windows doesn't allow executing a file opened by another process
    fd, temp_path = tempfile.mkstemp(suffix=".py", text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(clean_code)
        
        script_path = Path(temp_path)
        
        # 4. Build command (use current python executable)
        cmd = [sys.executable, str(script_path)]
        
        run_kwargs = _make_run_kwargs(
            limits,
            work_dir=script_path.parent,
            capture_output=True,
            text=True,
            timeout=limits.wall_seconds,
            env=_minimal_env(),
        )
        
        # 5. Execute
        result = subprocess.run(cmd, **run_kwargs)
        
        # 6. Truncate outputs to avoid huge logs
        from src.utils.cpp_execution import _truncate_output
        stdout = _truncate_output(result.stdout or "", max_chars=10000)
        stderr = _truncate_output(result.stderr or "", max_chars=10000)
        
        normalized_ret = result.returncode
        normalized_err = stderr
        if limits.cpu_seconds is not None and result.returncode in (-signal.SIGKILL, -signal.SIGXCPU):
            normalized_ret = 124
            normalized_err = "Time Limit Exceeded"

        return normalized_ret, stdout, normalized_err
        
    except subprocess.TimeoutExpired:
        return 124, "", f"Time Limit Exceeded: Python execution took longer than {limits.wall_seconds}s."
    except Exception as e:
        return -1, "", f"Execution Framework Error: {str(e)}"
    finally:
        # Cleanup temp file
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
