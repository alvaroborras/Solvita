"""Code Executor - LangGraph Compatible

Executes compiled code against test cases and returns state-compatible results.
"""

import subprocess
import time
from typing import Dict, List, Tuple, Any, Optional
from loguru import logger


class CodeExecutor:
    """Execute compiled code with test cases"""

    def __init__(self, timeout: int = 5, memory_limit_mb: int = 256):
        """
        Initialize code executor.

        Args:
            timeout: Maximum execution time per test (seconds)
            memory_limit_mb: Memory limit in MB
        """
        self.timeout = timeout
        self.memory_limit_mb = memory_limit_mb

    def run_tests(self, binary_path: str, tests: List[Dict]) -> Dict[str, Any]:
        """
        Run all test cases against compiled binary.

        Args:
            binary_path: Path to compiled executable
            tests: List of test case dicts

        Returns:
            Dict with fields for SolvitaState:
            - test_results: List[Dict] (per-test results)
            - passed_tests: int
            - failed_tests: int
            - pass_rate: float
        """
        logger.info(f"Running {len(tests)} test cases...")

        results = []
        passed = 0
        failed = 0

        for i, test in enumerate(tests):
            logger.debug(f"Running test {i+1}/{len(tests)}: {test.get('id', 'unknown')}")

            result = self.run_single_test(
                binary_path,
                test['input'],
                test.get('expected_output'),
                test.get('id', f'test_{i+1}')
            )

            results.append(result)

            if result['status'] == 'passed':
                passed += 1
            else:
                failed += 1

        pass_rate = passed / len(tests) if tests else 0.0

        logger.info(f"Test results: {passed}/{len(tests)} passed ({pass_rate:.1%})")

        return {
            "test_results": results,
            "passed_tests": passed,
            "failed_tests": failed,
            "pass_rate": pass_rate,
        }

    def run_single_test(self,
                       binary_path: str,
                       test_input: str,
                       expected_output: Optional[str],
                       test_id: str) -> Dict[str, Any]:
        """
        Run single test case.

        Args:
            binary_path: Path to executable
            test_input: Input data
            expected_output: Expected output (None if unknown)
            test_id: Test identifier

        Returns:
            Dict with test result details
        """
        try:
            start_time = time.time()

            result = subprocess.run(
                [binary_path],
                input=test_input,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            execution_time = time.time() - start_time

            actual_output = result.stdout.strip()
            stderr = result.stderr.strip()

            # Determine status
            if result.returncode != 0:
                status = "runtime_error"
                error = stderr if stderr else "Non-zero exit code"
            elif expected_output is not None:
                if self.compare_output(expected_output, actual_output):
                    status = "passed"
                    error = None
                else:
                    status = "wrong_answer"
                    error = f"Expected: {expected_output[:50]}..., Got: {actual_output[:50]}..."
            else:
                # No expected output to compare
                status = "executed"
                error = None

            return {
                "test_id": test_id,
                "status": status,
                "actual_output": actual_output,
                "expected_output": expected_output,
                "execution_time": execution_time,
                "error": error,
                "stderr": stderr,
            }

        except subprocess.TimeoutExpired:
            logger.warning(f"Test {test_id} timeout")
            return {
                "test_id": test_id,
                "status": "timeout",
                "actual_output": None,
                "expected_output": expected_output,
                "execution_time": self.timeout,
                "error": f"Time limit exceeded ({self.timeout}s)",
                "stderr": "",
            }

        except Exception as e:
            logger.error(f"Test {test_id} error: {e}")
            return {
                "test_id": test_id,
                "status": "error",
                "actual_output": None,
                "expected_output": expected_output,
                "execution_time": 0,
                "error": str(e),
                "stderr": "",
            }

    def compare_output(self, expected: str, actual: str) -> bool:
        """
        Compare expected and actual output.

        Handles:
        - Whitespace normalization
        - Trailing newlines
        - Multiple spaces

        Args:
            expected: Expected output
            actual: Actual output

        Returns:
            True if outputs match
        """
        if expected is None:
            return True  # No expected output to compare

        # Normalize whitespace
        expected_normalized = ' '.join(expected.strip().split())
        actual_normalized = ' '.join(actual.strip().split())

        return expected_normalized == actual_normalized

    def check_timeout(self, execution_time: float) -> bool:
        """Check if execution exceeded timeout"""
        return execution_time > self.timeout

