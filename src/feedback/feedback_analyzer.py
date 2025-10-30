"""Feedback Analyzer - LangGraph Compatible

Analyzes compilation errors and test failures to provide actionable feedback.
"""

from typing import Dict, List, Any, Optional
from collections import Counter
from loguru import logger


class FeedbackAnalyzer:
    """Analyze errors and failures to provide improvement suggestions"""

    def __init__(self, llm=None):
        """
        Initialize feedback analyzer.

        Args:
            llm: Optional LLM for intelligent feedback analysis
        """
        self.llm = llm

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
        """Analyze compilation errors"""
        logger.info(f"Analyzing {len(errors)} compilation errors")

        # Identify error types
        error_types = []
        for error in errors:
            error_lower = error.lower()
            if 'syntax' in error_lower or 'expected' in error_lower:
                error_types.append('syntax_error')
            elif 'undeclared' in error_lower or 'not declared' in error_lower:
                error_types.append('undeclared_identifier')
            elif 'type' in error_lower:
                error_types.append('type_error')
            else:
                error_types.append('other')

        # Count patterns
        pattern_counts = Counter(error_types)
        most_common = pattern_counts.most_common(1)[0][0] if pattern_counts else 'unknown'

        # Generate suggestions
        suggestions = []
        if 'syntax_error' in error_types:
            suggestions.append("Fix syntax errors: check brackets, semicolons, and parentheses")
        if 'undeclared_identifier' in error_types:
            suggestions.append("Declare all variables before using them")
        if 'type_error' in error_types:
            suggestions.append("Check type compatibility in assignments and function calls")

        if not suggestions:
            suggestions.append("Review and fix compilation errors")

        feedback = {
            "type": "compilation_error",
            "error_count": len(errors),
            "primary_errors": errors[:5],  # Show first 5 errors
            "dominant_pattern": most_common,
        }

        return {
            "feedback": feedback,
            "error_patterns": list(set(error_types)),
            "suggested_fixes": suggestions,
            "failure_analysis": {
                "stage": "compilation",
                "error_distribution": dict(pattern_counts),
            },
        }

    def _analyze_test_failures(self,
                              failed_tests: List[Dict],
                              all_tests: List[Dict],
                              code: str) -> Dict[str, Any]:
        """Analyze test failures"""
        logger.info(f"Analyzing {len(failed_tests)} test failures")

        # Categorize failures
        failure_types = Counter()
        for test in failed_tests:
            failure_types[test['status']] += 1

        # Identify patterns
        patterns = []
        if failure_types.get('wrong_answer', 0) > 0:
            patterns.append('incorrect_logic')
        if failure_types.get('timeout', 0) > 0:
            patterns.append('performance_issue')
        if failure_types.get('runtime_error', 0) > 0:
            patterns.append('runtime_error')

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
            suggestions.append(f"Consider more efficient data structures")

        if 'runtime_error' in patterns:
            suggestions.append("Check array bounds and null pointer access")
            suggestions.append("Verify input parsing logic")

        if not suggestions:
            suggestions.append("Review failed test cases and adjust algorithm logic")

        # Create feedback summary
        feedback = {
            "type": "test_failure",
            "failed_count": len(failed_tests),
            "total_count": len(all_tests),
            "failure_rate": len(failed_tests) / len(all_tests),
            "failure_types": dict(failure_types),
            "example_failures": failed_tests[:3],  # Show first 3 failures
        }

        failure_analysis = {
            "stage": "testing",
            "patterns_detected": patterns,
            "failure_distribution": dict(failure_types),
            "affected_categories": dict(Counter([t.get('category', 'unknown') for t in failed_tests])),
        }

        return {
            "feedback": feedback,
            "error_patterns": patterns,
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

