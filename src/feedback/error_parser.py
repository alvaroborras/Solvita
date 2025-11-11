"""Error Parser - Parse compilation, runtime, and test errors"""

import re
from typing import Dict, Optional, List
from loguru import logger


class ErrorParser:
    """Parse compilation and runtime errors from C++ code"""

    def __init__(self):
        """Initialize error parser with error patterns"""
        # Common C++ error patterns
        self.error_patterns = {
            "undefined_reference": r"undefined reference to",
            "undeclared": r"'(\w+)' was not declared",
            "syntax_error": r"error: (expected|syntax|invalid)",
            "type_error": r"(error: cannot|error: no matching|error: invalid conversion)",
            "segfault": r"(Segmentation fault|core dumped|signal 11)",
            "abort": r"(Aborted|signal 6|SIGABRT)",
            "timeout": r"(Time limit|timeout|TLE)",
            "memory_limit": r"(Memory limit|MLE|exceeded)",
        }

        # Compilation error severity levels
        self.error_categories = {
            "syntax": ["syntax_error", "expected"],
            "undefined": ["undefined_reference", "undeclared"],
            "type": ["type_error"],
            "runtime": ["segfault", "abort"],
        }

    def parse_compilation_error(self, stderr: str) -> Dict:
        """
        Parse C++ compilation error from g++ stderr.

        Args:
            stderr: Error output from g++ compiler

        Returns:
            Dict with:
            - error_type: Type of error (Syntax, Undefined, Type, etc.)
            - line_number: Line where error occurred
            - message: Full error message
            - file: Filename
            - column: Column number
            - suggestion: Potential fix suggestion
        """
        if not stderr or not stderr.strip():
            return {
                "error_type": "Unknown",
                "line_number": None,
                "message": "No error information provided",
                "file": "unknown",
                "column": None,
                "suggestion": "Check code for issues"
            }

        result = {
            "error_type": "Compilation Error",
            "line_number": None,
            "message": stderr.strip(),
            "file": "unknown",
            "column": None,
            "suggestion": None
        }

        lines = stderr.strip().split('\n')
        first_error = lines[0] if lines else ""

        # Extract file, line, column from g++ format: "file.cpp:line:column: error: message"
        match = re.match(r"(.+?):(\d+):(\d+):\s*(error|warning):\s*(.+)", first_error)
        if match:
            result["file"] = match.group(1)
            result["line_number"] = int(match.group(2))
            result["column"] = int(match.group(3))
            result["message"] = match.group(5)

        # Categorize error
        error_category = self._categorize_compilation_error(stderr)
        result["error_type"] = error_category

        # Generate suggestion
        result["suggestion"] = self._suggest_compilation_fix(error_category, stderr)

        logger.debug(f"Parsed compilation error: line {result['line_number']}, type: {result['error_type']}")
        return result

    def parse_runtime_error(self, stderr: str, test: Dict) -> Dict:
        """
        Parse runtime error from program execution.

        Args:
            stderr: Error output from running program
            test: Test case dict with 'input' and expected 'output'

        Returns:
            Dict with:
            - error_type: Type of runtime error
            - message: Error message
            - test_input: The input that caused error
            - possible_cause: Analysis of what caused the error
        """
        result = {
            "error_type": "Runtime Error",
            "message": stderr.strip() if stderr else "Unknown runtime error",
            "test_input": test.get("input", "")[:100] + "..." if len(test.get("input", "")) > 100 else test.get("input", ""),
            "possible_cause": None
        }

        # Detect segmentation fault
        if re.search(r"Segmentation fault|core dumped|signal 11", stderr or ""):
            result["error_type"] = "Segmentation Fault"
            result["possible_cause"] = "Array out of bounds, null pointer dereference, or stack overflow"

        # Detect abort
        elif re.search(r"Aborted|signal 6|SIGABRT", stderr or ""):
            result["error_type"] = "Abort Signal"
            result["possible_cause"] = "Assertion failure, std::bad_alloc, or other runtime assertion"

        # Detect floating point error
        elif re.search(r"signal 8|Floating point exception", stderr or ""):
            result["error_type"] = "Floating Point Error"
            result["possible_cause"] = "Division by zero or invalid math operation"

        # Generic runtime error
        else:
            result["error_type"] = "Runtime Error"
            result["possible_cause"] = "Check input parsing and array/pointer access"

        logger.debug(f"Parsed runtime error: {result['error_type']}")
        return result

    def parse_wrong_answer(self, expected: str, actual: str, test: Dict) -> Dict:
        """
        Parse wrong answer by comparing expected vs actual output.

        Args:
            expected: Expected output
            actual: Actual output from program
            test: Test case dict

        Returns:
            Dict with:
            - error_type: "Wrong Answer"
            - expected: Expected output (first 200 chars)
            - actual: Actual output (first 200 chars)
            - difference: Where outputs differ
            - test_input: Test input (first 200 chars)
        """
        expected_str = expected.strip() if expected else ""
        actual_str = actual.strip() if actual else ""

        result = {
            "error_type": "Wrong Answer",
            "expected": expected_str[:200] + "..." if len(expected_str) > 200 else expected_str,
            "actual": actual_str[:200] + "..." if len(actual_str) > 200 else actual_str,
            "test_input": str(test.get("input", ""))[:200] + "..." if len(str(test.get("input", ""))) > 200 else str(test.get("input", "")),
            "difference": None
        }

        # Find first difference
        expected_lines = expected_str.split('\n')
        actual_lines = actual_str.split('\n')

        for i, (exp, act) in enumerate(zip(expected_lines, actual_lines)):
            if exp != act:
                result["difference"] = f"Line {i+1}: expected '{exp}', got '{act}'"
                break

        if not result["difference"]:
            if len(expected_lines) != len(actual_lines):
                result["difference"] = f"Different number of lines: expected {len(expected_lines)}, got {len(actual_lines)}"
            else:
                result["difference"] = "Outputs differ but exact difference unclear"

        logger.debug(f"Parsed wrong answer: {result['difference']}")
        return result

    def extract_error_location(self, error_message: str) -> Optional[int]:
        """
        Extract line number from error message.

        Args:
            error_message: Error message string

        Returns:
            Line number if found, None otherwise
        """
        if not error_message:
            return None

        # Match g++ format: "file.cpp:123:45: error: message"
        match = re.search(r":(\d+):", error_message)
        if match:
            return int(match.group(1))

        # Match patterns like "line 123" or "at line 123"
        match = re.search(r"(?:line|at line|at)\s+(\d+)", error_message, re.IGNORECASE)
        if match:
            return int(match.group(1))

        return None

    def categorize_error(self, error: Dict) -> str:
        """
        Categorize error type (Syntax, Logic, TLE, MLE, Runtime, WA, etc.).

        Args:
            error: Error dict with 'error_type' and 'message' fields

        Returns:
            Categorized error type string
        """
        error_type = error.get("error_type", "Unknown").lower()
        message = (error.get("message", "") + error.get("possible_cause", "")).lower()

        # Check for specific error types
        if "syntax" in error_type or "syntax" in message or "expected" in message:
            return "Syntax Error"

        if "undefined" in error_type or "undefined reference" in message:
            return "Undefined Reference"

        if "type" in error_type or "type error" in message or "no matching" in message:
            return "Type Error"

        if "segmentation" in error_type or "segfault" in error_type:
            return "Segmentation Fault"

        if "abort" in error_type or "signal" in error_type:
            return "Runtime Abort"

        if "floating" in error_type or "division by zero" in message:
            return "Floating Point Error"

        if "timeout" in error_type or "time limit" in message or "tle" in message:
            return "Time Limit Exceeded"

        if "memory" in error_type or "mle" in message or "bad_alloc" in message:
            return "Memory Limit Exceeded"

        if "wrong answer" in error_type:
            return "Wrong Answer"

        if "compilation" in error_type:
            return "Compilation Error"

        if "runtime" in error_type:
            return "Runtime Error"

        return "Unknown Error"

    def _categorize_compilation_error(self, stderr: str) -> str:
        """
        Internal method to categorize compilation errors.

        Args:
            stderr: Compiler error output

        Returns:
            Error category
        """
        stderr_lower = stderr.lower()

        if "undefined reference" in stderr_lower:
            return "Undefined Reference"
        elif "not declared" in stderr_lower or "undeclared" in stderr_lower:
            return "Undeclared Variable"
        elif "expected" in stderr_lower or "syntax" in stderr_lower:
            return "Syntax Error"
        elif "type" in stderr_lower or "conversion" in stderr_lower:
            return "Type Error"
        elif "no matching" in stderr_lower:
            return "No Matching Function"
        else:
            return "Compilation Error"

    def _suggest_compilation_fix(self, error_category: str, error_message: str) -> str:
        """
        Internal method to suggest fixes for compilation errors.

        Args:
            error_category: Category of error
            error_message: Full error message

        Returns:
            Suggestion string
        """
        suggestions = {
            "Syntax Error": "Check for missing semicolons, brackets, or quotation marks",
            "Undefined Reference": "Check if function is defined, linked correctly, or #include added",
            "Undeclared Variable": "Add #include for header files or declare the variable",
            "Type Error": "Check data types match in assignments and function calls",
            "No Matching Function": "Check function signature matches parameters",
        }

        return suggestions.get(error_category, "Review error message and check code syntax")

