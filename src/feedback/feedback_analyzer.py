"""Feedback Analyzer - LangGraph Compatible

Analyzes compilation errors and test failures to provide actionable feedback.
Uses ErrorParser for intelligent error classification.
"""

from typing import Dict, List, Any, Optional
from collections import Counter
from loguru import logger
from .error_parser import ErrorParser


class FeedbackAnalyzer:
    """Analyze errors and failures to provide improvement suggestions"""

    def __init__(self, llm=None):
        """
        Initialize feedback analyzer.

        Args:
            llm: Optional LLM for intelligent feedback analysis
        """
        self.llm = llm
        self.error_parser = ErrorParser()

    def analyze(self,
               generated_code: str,
               compilation_errors: List[str],
               test_results: List[Dict]) -> Dict[str, Any]:
        """
        Analyze compilation errors and test results.

        Args:
            generated_code: The C++ code that was tested
            compilation_errors: List of compilation error messages
            test_results: List of test result dicts

        Returns:
            Dict with fields for SolvitaState:
            - feedback: Structured feedback
            - error_patterns: List of identified patterns
            - suggested_fixes: List of suggested fixes
            - failure_analysis: Detailed analysis
        """
        logger.info("Analyzing feedback...")

        # Handle compilation errors first
        if compilation_errors:
            return self._analyze_compilation_errors(compilation_errors, generated_code)

        # Handle test failures
        failed_tests = [t for t in test_results if t['status'] != 'passed']

        if not failed_tests:
            return {
                "feedback": {"type": "success", "message": "All tests passed"},
                "error_patterns": [],
                "suggested_fixes": [],
                "failure_analysis": {},
            }

        return self._analyze_test_failures(failed_tests, test_results, generated_code)

    def _analyze_compilation_errors(self, errors: List[str], code: str) -> Dict[str, Any]:
        """Analyze compilation errors using ErrorParser"""
        logger.info(f"Analyzing {len(errors)} compilation errors")

        if not errors:
            return {
                "feedback": {"type": "no_errors", "message": "No compilation errors"},
                "error_patterns": [],
                "suggested_fixes": [],
                "failure_analysis": {"stage": "compilation", "error_distribution": {}},
            }

        # Combine all errors for comprehensive parsing
        combined_stderr = "\n".join(errors)

        # Use ErrorParser for intelligent analysis
        parsed_error = self.error_parser.parse_compilation_error(combined_stderr)

        # Extract error details
        error_type = parsed_error.get("error_type", "Unknown")
        line_number = parsed_error.get("line_number")
        suggestion = parsed_error.get("suggestion", "")

        # Categorize multiple errors
        error_categories = []
        for error in errors:
            categorized = self.error_parser.categorize_error({
                "error_type": error_type,
                "message": error
            })
            error_categories.append(categorized)

        # Count patterns
        pattern_counts = Counter(error_categories)
        most_common = pattern_counts.most_common(1)[0][0] if pattern_counts else "Unknown Error"

        # Generate suggestions based on parsed errors
        suggestions = []
        if suggestion:
            suggestions.append(suggestion)

        # Add specific suggestions based on error type
        if "Syntax" in error_type:
            suggestions.append("Check for missing semicolons, brackets, or parentheses")
            if line_number:
                suggestions.append(f"Review code around line {line_number}")
        elif "Undefined" in error_type:
            suggestions.append("Ensure function is defined or header is included")
        elif "Type" in error_type:
            suggestions.append("Verify data types match in operations")

        if not suggestions:
            suggestions.append("Review and fix compilation errors")

        # Build structured feedback
        feedback = {
            "type": "compilation_error",
            "error_count": len(errors),
            "primary_error_type": error_type,
            "line_number": line_number,
            "dominant_pattern": most_common,
            "sample_errors": errors[:3],  # Show first 3 errors
        }

        failure_analysis = {
            "stage": "compilation",
            "error_distribution": dict(pattern_counts),
            "primary_error": parsed_error,
            "error_categories": list(set(error_categories)),
        }

        return {
            "feedback": feedback,
            "error_patterns": list(set(error_categories)),
            "suggested_fixes": suggestions,
            "failure_analysis": failure_analysis,
        }

    def _analyze_test_failures(self,
                              failed_tests: List[Dict],
                              all_tests: List[Dict],
                              code: str) -> Dict[str, Any]:
        """Analyze test failures using ErrorParser for runtime errors and WA analysis"""
        logger.info(f"Analyzing {len(failed_tests)} test failures")

        # Categorize failures
        failure_types = Counter()
        error_details = []

        for test in failed_tests:
            status = test.get('status', 'unknown')
            failure_types[status] += 1

            # Use ErrorParser for detailed analysis
            if status == 'runtime_error':
                stderr = test.get('stderr', '')
                parsed = self.error_parser.parse_runtime_error(stderr, test)
                error_details.append(parsed)
            elif status == 'wrong_answer':
                expected = test.get('expected_output', '')
                actual = test.get('actual_output', '')
                parsed = self.error_parser.parse_wrong_answer(expected, actual, test)
                error_details.append(parsed)

        # Identify patterns
        patterns = []
        if failure_types.get('wrong_answer', 0) > 0:
            patterns.append('incorrect_logic')
        if failure_types.get('timeout', 0) > 0:
            patterns.append('performance_issue')
        if failure_types.get('runtime_error', 0) > 0:
            patterns.append('runtime_error')

        # Categorize errors using ErrorParser
        categorized_errors = []
        for error_detail in error_details:
            cat = self.error_parser.categorize_error(error_detail)
            categorized_errors.append(cat)

        # Generate suggestions based on patterns
        suggestions = []

        if 'incorrect_logic' in patterns:
            # Analyze which test categories are failing
            failed_categories = [t.get('category', 'unknown') for t in failed_tests]
            category_counts = Counter(failed_categories)

            if category_counts.get('edge_case', 0) > 0:
                suggestions.append("Review edge case handling (min/max values)")
            if category_counts.get('corner_case', 0) > 0:
                suggestions.append("Handle special cases (empty input, single element, etc.)")
            if category_counts.get('random', 0) > 0:
                suggestions.append("Review general algorithm logic")

        if 'performance_issue' in patterns:
            suggestions.append("Optimize algorithm: reduce time complexity")
            suggestions.append("Consider more efficient data structures (hash map, segment tree, etc.)")

        if 'runtime_error' in patterns:
            # Provide specific suggestions based on runtime error types
            runtime_error_types = Counter([e.get('error_type', 'Unknown') for e in error_details])
            if runtime_error_types.get('Segmentation Fault', 0) > 0:
                suggestions.append("Fix segmentation fault: check array bounds and pointer safety")
            if runtime_error_types.get('Abort Signal', 0) > 0:
                suggestions.append("Fix abort signal: check assertions and memory allocation")
            if not suggestions or len(suggestions) == 1:
                suggestions.append("Check array bounds and null pointer access")
                suggestions.append("Verify input parsing logic")

        if not suggestions:
            suggestions.append("Review failed test cases and adjust algorithm logic")

        # Create feedback summary
        feedback = {
            "type": "test_failure",
            "failed_count": len(failed_tests),
            "total_count": len(all_tests),
            "failure_rate": len(failed_tests) / len(all_tests) if all_tests else 0,
            "failure_types": dict(failure_types),
            "example_failures": failed_tests[:3],  # Show first 3 failures
        }

        failure_analysis = {
            "stage": "testing",
            "patterns_detected": patterns,
            "failure_distribution": dict(failure_types),
            "affected_categories": dict(Counter([t.get('category', 'unknown') for t in failed_tests])),
            "error_details": error_details[:5],  # Show first 5 error details
            "error_categories": dict(Counter(categorized_errors)),
        }

        return {
            "feedback": feedback,
            "error_patterns": list(set(categorized_errors)) if categorized_errors else patterns,
            "suggested_fixes": suggestions,
            "failure_analysis": failure_analysis,
        }

    def identify_error_pattern(self, failed_tests: List[Dict]) -> str:
        """Identify dominant error pattern"""
        if not failed_tests:
            return "none"

        status_counts = Counter([t['status'] for t in failed_tests])
        return status_counts.most_common(1)[0][0]

    def analyze_performance(self, test_results: List[Dict]) -> Dict[str, Any]:
        """Analyze performance metrics"""
        execution_times = [
            t.get('execution_time', 0)
            for t in test_results
            if t.get('execution_time') is not None
        ]

        if not execution_times:
            return {}

        return {
            "avg_time": sum(execution_times) / len(execution_times),
            "max_time": max(execution_times),
            "min_time": min(execution_times),
            "total_tests": len(test_results),
        }

