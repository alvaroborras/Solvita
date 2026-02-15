"""Compile Code Node - Compile C++ code with sandboxed execution"""

import tempfile
import platform
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING
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
    src_path = tmp_dir / "solution.cpp"
    exe_path = tmp_dir / "solution"

    src_path.write_text(code, encoding="utf-8")

    # Choose limits: diagnostic mode uses sanitizers, normal mode uses -O2
    diagnostic = state.get("solution", {}).get("diagnostic_mode", False)
    limits = ExecutionLimits.diagnostic_compile() if diagnostic else ExecutionLimits.default_compile()

    ok, output = compile_cpp(src_path, exe_path, limits=limits, diagnostic=diagnostic)

    updated_solution = dict(state["solution"])

    if ok:
        # On Windows, g++ automatically adds .exe extension
        # Update the path to match the actual executable
        if platform.system() == "Windows" and not exe_path.suffix:
            actual_exe_path = exe_path.with_suffix(".exe")
        else:
            actual_exe_path = exe_path
        
        updated_solution.update({
            "compilation_success": True,
            "compilation_errors": [],
            "executable_path": str(actual_exe_path),
        })
        log_msg = "Code compiled successfully"
        if diagnostic:
            log_msg += " (diagnostic / sanitizer mode)"
        return {
            "solution": updated_solution,
            "execution_log": [log_msg],
        }
    else:
        errors = _parse_compilation_errors(output)
        updated_solution.update({
            "compilation_success": False,
            "compilation_errors": errors,
            "executable_path": None,
        })
        return {
            "solution": updated_solution,
            "execution_log": [f"Compilation failed: {len(errors)} error(s)"],
        }


def _parse_compilation_errors(output: str) -> list[str]:
    """Extract meaningful error/warning lines from compiler output."""
    errors = []
    for line in output.split("\n"):
        line = line.strip()
        if line and ("error:" in line.lower() or "warning:" in line.lower()):
            errors.append(line)
    return errors if errors else [output[:2000]]
