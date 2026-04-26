"""Compile Code Node - Compile C++ code with sandboxed execution"""

import tempfile
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING, Optional
from loguru import logger
from src.utils.cpp_execution import compile_cpp, ExecutionLimits

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def compile_code_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Compile C++ code using the sandboxed compile_cpp utility.
    
    Returns:
    - compilation_success: bool
    - compilation_errors: list of error messages
    - executable_path: path to compiled binary (if success)
    """
    logger.info("[Node] Compiling C++ code")
    
    code = state["solution"].get("code", "")
    if not code.strip():
        updated_solution = dict(state["solution"])
        updated_solution.update({
            "compilation_success": False,
            "compilation_errors": ["No code to compile"],
            "executable_path": None,
        })
        return {
            "solution": updated_solution,
            "execution_log": ["Compilation skipped: no code"],
        }

    # Use a persistent temp directory (not auto-deleted) so the executable
    # survives for downstream run_tests_node.  Cleanup happens at workflow end.
    tmp_dir = Path(tempfile.mkdtemp(prefix="solvita_compile_"))

    # Choose limits: diagnostic mode uses sanitizers, normal mode uses -O2
    diagnostic = state.get("solution", {}).get("diagnostic_mode", False)
    limits = ExecutionLimits.diagnostic_compile() if diagnostic else ExecutionLimits.default_compile()

    exe_path, errors = prepare_executable(code, "C++", tmp_dir, diagnostic, limits)

    updated_solution = dict(state["solution"])

    if exe_path:
        updated_solution.update({
            "compilation_success": True,
            "compilation_errors": [],
            "executable_path": str(exe_path),
            "compile_fail_streak": 0,
        })
        log_msg = "Code compiled successfully"
        if diagnostic:
            log_msg += " (diagnostic / sanitizer mode)"
        return {
            "solution": updated_solution,
            "execution_log": [log_msg],
        }
    else:
        prior_streak = int(state.get("solution", {}).get("compile_fail_streak", 0) or 0)
        new_streak = prior_streak + 1
        updated_solution.update({
            "compilation_success": False,
            "compilation_errors": errors,
            "executable_path": None,
            "compile_fail_streak": new_streak,
        })
        cap = int((state.get("config", {}) or {}).get("max_compile_fail_streak", 8))
        update: Dict[str, Any] = {
            "solution": updated_solution,
            "execution_log": [f"Compilation failed: {len(errors)} error(s)"],
        }
        if new_streak >= cap:
            update["status"] = "max_iterations"
            update["iteration"] = int(state.get("max_iterations", 5))
            update["execution_log"] = [
                f"Compilation failed: {len(errors)} error(s)",
                f"✗ Compile failure streak reached {new_streak} (cap={cap}); giving up.",
            ]
        return update

def prepare_executable(code: str, lang: str, tmp_dir: Path, diagnostic: bool = False, limits: Optional[ExecutionLimits] = None) -> tuple[Optional[Path], list[str]]:
    """
    Prepare an executable from source code.
    For C++, writes to a .cpp file and compiles it.
    For Python 3, writes to a .py file, adds a shebang, and makes it executable.
    
    Returns:
    - executable_path (if successful)
    - list of error messages (if failed)
    """
    if lang.lower() in ("c++", "cpp"):
        src_path = tmp_dir / "solution.cpp"
        exe_path = tmp_dir / "solution"
        src_path.write_text(code, encoding="utf-8")
        
        ok, output = compile_cpp(src_path, exe_path, limits=limits, diagnostic=diagnostic)
        if ok:
            actual_exe_path = exe_path
            # On Windows, g++ emits solution.exe even if "-o solution" is passed.
            if not actual_exe_path.exists():
                windows_exe_path = exe_path.with_suffix(".exe")
                if windows_exe_path.exists():
                    actual_exe_path = windows_exe_path
            return actual_exe_path, []
        else:
            return None, _parse_compilation_errors(output)
            
    elif lang.lower() in ("python", "python3", "python 3"):
        exe_path = tmp_dir / "solution.py"
        
        # Ensure it starts with python3 shebang
        code_lines = code.splitlines()
        if not code_lines or not code_lines[0].startswith("#!"):
            code = "#!/usr/bin/env python3\n" + code
            
        exe_path.write_text(code, encoding="utf-8")
        
        # Make the script executable
        try:
            exe_path.chmod(exe_path.stat().st_mode | 0o111)
            return exe_path, []
        except Exception as e:
            return None, [f"Failed to make Python script executable: {e}"]
            
    else:
        return None, [f"Unsupported language: {lang}"]


def _parse_compilation_errors(output: str) -> list[str]:
    """Extract meaningful error/warning lines from compiler output."""
    errors = []
    for line in output.split("\n"):
        line = line.strip()
        if line and ("error:" in line.lower() or "warning:" in line.lower()):
            errors.append(line)
    return errors if errors else [output[:2000]]
