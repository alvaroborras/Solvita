"""C++ Compiler - LangGraph Compatible

Compiles C++ code and returns state-compatible results.
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, Tuple, Any, Optional, List
from loguru import logger


class CPPCompiler:
    """Compile C++ code using g++ compiler"""

    def __init__(self, compiler: str = "g++", flags: Optional[List[str]] = None):
        """
        Initialize C++ compiler.

        Args:
            compiler: Compiler command (default: g++)
            flags: Default compilation flags
        """
        self.compiler = compiler
        self.default_flags = flags or ["-std=c++17", "-O2", "-Wall"]

    def compile(self, source_code: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Compile C++ source code.

        Args:
            source_code: C++ source code string
            output_path: Optional output path for executable

        Returns:
            Dict with fields for SolvitaState:
            - compilation_success: bool
            - compilation_errors: List[str]
            - compiler_output: str
            - executable_path: Optional[str]
        """
        logger.info("Compiling C++ code...")

        # Create temporary source file
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.cpp',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(source_code)
                cpp_file = f.name

            # Determine output path
            if output_path is None:
                output_path = cpp_file.replace('.cpp', '')

            # Compile
            cmd = [self.compiler] + self.default_flags + [cpp_file, '-o', output_path]

            logger.debug(f"Compile command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            # Clean up source file
            try:
                os.unlink(cpp_file)
            except:
                pass

            if result.returncode == 0:
                logger.info(f"✓ Compilation successful: {output_path}")
                return {
                    "compilation_success": True,
                    "compilation_errors": [],
                    "compiler_output": result.stdout + result.stderr,
                    "executable_path": output_path,
                }
            else:
                errors = self.parse_compilation_errors(result.stderr)
                logger.warning(f"✗ Compilation failed with {len(errors)} errors")
                return {
                    "compilation_success": False,
                    "compilation_errors": errors,
                    "compiler_output": result.stderr,
                    "executable_path": None,
                }

        except subprocess.TimeoutExpired:
            logger.error("Compilation timeout")
            return {
                "compilation_success": False,
                "compilation_errors": ["Compilation timeout exceeded"],
                "compiler_output": "Timeout",
                "executable_path": None,
            }

        except Exception as e:
            logger.error(f"Compilation error: {e}")
            return {
                "compilation_success": False,
                "compilation_errors": [str(e)],
                "compiler_output": str(e),
                "executable_path": None,
            }

    def compile_with_flags(self, source_code: str, flags: List[str]) -> Dict[str, Any]:
        """
        Compile with custom flags.

        Args:
            source_code: C++ source code
            flags: Custom compiler flags

        Returns:
            Same as compile()
        """
        original_flags = self.default_flags
        self.default_flags = flags
        result = self.compile(source_code)
        self.default_flags = original_flags
        return result

    def parse_compilation_errors(self, stderr: str) -> List[str]:
        """
        Parse compilation error messages.

        Args:
            stderr: Compiler error output

        Returns:
            List of error messages
        """
        if not stderr:
            return []

        errors = []
        for line in stderr.split('\n'):
            line = line.strip()
            if line and ('error:' in line.lower() or 'warning:' in line.lower()):
                errors.append(line)

        return errors if errors else [stderr]

    def check_compiler_available(self) -> bool:
        """Check if compiler is available"""
        try:
            result = subprocess.run(
                [self.compiler, '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

