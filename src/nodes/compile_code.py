"""Compile Code Node - Compile C++ code"""

from typing import Dict, Any
import subprocess
import tempfile
import os
from loguru import logger
from src.graph.state import SolvitaState


def compile_code_node(state: SolvitaState) -> Dict[str, Any]:
    """
    Compile C++ code using g++
    
    Returns:
    - compilation_success: bool
    - compilation_errors: list of error messages
    - executable_path: path to compiled binary (if success)
    """
    logger.info("[Node] Compiling C++ code")
    
    code = state['solution'].get('code', '')
    
    # Create temporary files for source and executable
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as src_file:
        src_file.write(code)
        src_path = src_file.name
    
    exe_path = src_path.replace('.cpp', '.out')
    
    try:
        # Compile with g++
        result = subprocess.run(
            ['g++', '-std=c++17', '-O2', src_path, '-o', exe_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Compilation successful
            return {
                "solution": {
                    "compilation_success": True,
                    "compilation_errors": [],
                    "executable_path": exe_path,
                },
                "execution_log": ["✓ Code compiled successfully"],
            }
        else:
            # Compilation failed
            errors = _parse_compilation_errors(result.stderr)
            return {
                "solution": {
                    "compilation_success": False,
                    "compilation_errors": errors,
                    "executable_path": None,
                },
                "execution_log": [f"✗ Compilation failed: {len(errors)} errors"],
            }
    
    except subprocess.TimeoutExpired:
        return {
            "solution": {
                "compilation_success": False,
                "compilation_errors": ["Compilation timeout"],
                "executable_path": None,
            },
            "execution_log": ["✗ Compilation timeout"],
        }
    except Exception as e:
        return {
            "solution": {
                "compilation_success": False,
                "compilation_errors": [str(e)],
                "executable_path": None,
            },
            "execution_log": [f"✗ Compilation error: {e}"],
        }
    finally:
        # Clean up source file
        try:
            os.unlink(src_path)
        except:
            pass


def _parse_compilation_errors(stderr: str) -> list[str]:
    """Parse g++ error messages"""
    errors = []
    for line in stderr.split('\n'):
        line = line.strip()
        if line and ('error:' in line.lower() or 'warning:' in line.lower()):
            errors.append(line)
    return errors if errors else [stderr]

