"""Test Case Validator - Validate test cases against problem constraints"""

import re
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger


class TestValidator:
    """Validate generated test cases against problem constraints"""

    def __init__(self):
        """Initialize test validator with validation rules"""
        # Common constraint patterns
        self.constraint_patterns = {
            "array_size": r"(\d+)\s*(?:≤|<=|<)\s*n\s*(?:≤|<=|<)\s*(\d+)",
            "value_range": r"(\d+)\s*(?:≤|<=|<)\s*a_i\s*(?:≤|<=|<)\s*(\d+)",
            "integer_range": r"(\d+)\s*(?:≤|<=|<)\s*(?:x|val)\s*(?:≤|<=|<)\s*(\d+)",
        }

    def validate(self, test: Dict, constraints: Dict) -> bool:
        """
        Validate test case against constraints.

        Args:
            test: Test case dict with 'input' and 'output' keys
            constraints: Problem constraints dict

        Returns:
            True if test is valid, False otherwise
        """
        if not test or not isinstance(test, dict):
            logger.warning("Test is not a valid dict")
            return False

        if "input" not in test or "output" not in test:
            logger.warning("Test missing 'input' or 'output' key")
            return False

        # Validate input format
        if not self.validate_input_format(test.get("input", ""), constraints):
            logger.warning(f"Invalid input format: {test.get('input', '')[:100]}")
            return False

        # Validate output format
        if not self.validate_output_format(test.get("output", ""), constraints):
            logger.warning(f"Invalid output format: {test.get('output', '')[:100]}")
            return False

        # Validate constraints
        if not self.validate_constraints(test, constraints):
            logger.warning(f"Test violates constraints")
            return False

        logger.debug("Test case validated successfully")
        return True

    def validate_input_format(self, test_input: str, constraints: Dict) -> bool:
        """
        Validate test input format against problem format.

        Args:
            test_input: Input string from test case
            constraints: Problem constraints dict

        Returns:
            True if input format is valid, False otherwise
        """
        if not test_input or not isinstance(test_input, str):
            logger.warning("Test input is empty or not a string")
            return False

        test_input = test_input.strip()
        if not test_input:
            logger.warning("Test input is empty after stripping")
            return False

        # Try to parse as lines
        lines = test_input.split('\n')
        if len(lines) == 0:
            logger.warning("Test input has no lines")
            return False

        # Validate first line if it should be an integer (common pattern for array size)
        first_line = lines[0].strip()
        try:
            n = int(first_line)
            if n < 0:
                logger.warning(f"Array size cannot be negative: {n}")
                return False
            if n > 1000000:
                logger.warning(f"Array size too large: {n}")
                return False
        except ValueError:
            # First line might not be an integer, which is okay for some problems
            pass

        # Check if input has reasonable length (not empty after first line)
        if len(lines) == 1 and first_line.isdigit() and int(first_line) > 0:
            # If n is specified and > 0, there should be more data
            logger.warning(f"Input specifies {first_line} elements but no data provided")
            return False

        # Validate that input contains reasonable data
        try:
            for i, line in enumerate(lines[1:min(4, len(lines))]):
                line = line.strip()
                if line:
                    # Try to parse as numbers
                    parts = line.split()
                    for part in parts[:5]:  # Check first 5 elements
                        try:
                            float(part)
                        except ValueError:
                            # Not a number, might be a string - that's okay
                            pass
        except Exception as e:
            logger.warning(f"Error parsing input: {e}")
            return False

        return True

    def validate_output_format(self, test_output: str, constraints: Dict) -> bool:
        """
        Validate test output format.

        Args:
            test_output: Output string from test case
            constraints: Problem constraints dict

        Returns:
            True if output format is valid, False otherwise
        """
        if not test_output or not isinstance(test_output, str):
            logger.warning("Test output is empty or not a string")
            return False

        test_output = test_output.strip()
        if not test_output:
            logger.warning("Test output is empty after stripping")
            return False

        # Check output length (not too long)
        if len(test_output) > 100000:
            logger.warning(f"Output too long: {len(test_output)} characters")
            return False

        # Output should have reasonable structure
        lines = test_output.split('\n')
        if len(lines) > 10000:
            logger.warning(f"Output has too many lines: {len(lines)}")
            return False

        return True

    def validate_constraints(self, test: Dict, constraints: Dict) -> bool:
        """
        Validate test case satisfies all constraints.

        Args:
            test: Test case dict with 'input'
            constraints: Problem constraints dict with 'variables' list

        Returns:
            True if test satisfies constraints, False otherwise
        """
        if not constraints or not constraints.get("variables"):
            logger.debug("No constraints to validate")
            return True

        test_input = test.get("input", "").strip()
        lines = test_input.split('\n')

        # Extract constraint variables
        variables = constraints.get("variables", [])

        try:
            # Validate each constraint
            for var in variables:
                if not isinstance(var, dict):
                    continue

                var_name = var.get("name", "")
                min_val = var.get("min", 1)
                max_val = var.get("max", 100)

                # Try to extract value from input
                if var_name == "n" and lines:
                    try:
                        n = int(lines[0].strip())
                        if n < min_val or n > max_val:
                            logger.warning(f"Constraint violation: n={n} not in [{min_val}, {max_val}]")
                            return False
                    except (ValueError, IndexError):
                        pass

                # Check array elements if applicable
                if "array" in var_name.lower() and len(lines) > 1:
                    try:
                        elements = []
                        for line in lines[1:]:
                            parts = line.strip().split()
                            for part in parts:
                                try:
                                    elements.append(int(part))
                                except ValueError:
                                    try:
                                        elements.append(float(part))
                                    except ValueError:
                                        pass

                        # Validate array element values
                        for elem in elements:
                            if elem < min_val or elem > max_val:
                                logger.warning(f"Constraint violation: element {elem} not in [{min_val}, {max_val}]")
                                return False
                    except Exception as e:
                        logger.debug(f"Could not validate array elements: {e}")

        except Exception as e:
            logger.warning(f"Error validating constraints: {e}")
            return False

        return True

    def filter_invalid_tests(self, tests: List[Dict], constraints: Dict) -> Tuple[List[Dict], int]:
        """
        Filter out invalid test cases.

        Args:
            tests: List of test case dicts
            constraints: Problem constraints dict

        Returns:
            Tuple of (valid_tests, num_filtered)
        """
        if not tests:
            logger.debug("No tests to filter")
            return [], 0

        if not isinstance(tests, list):
            logger.warning("Tests is not a list")
            return [], len(tests) if tests else 0

        valid_tests = []
        invalid_count = 0

        for i, test in enumerate(tests):
            if self.validate(test, constraints):
                valid_tests.append(test)
            else:
                invalid_count += 1
                logger.debug(f"Filtered out invalid test {i+1}")

        logger.info(f"Filtered tests: {len(valid_tests)} valid, {invalid_count} invalid")
        return valid_tests, invalid_count

    def _extract_constraint_value(self,
                                   constraint_str: str,
                                   variable: str) -> Optional[Tuple[int, int]]:
        """
        Extract min/max values from constraint string.

        Args:
            constraint_str: Constraint description string
            variable: Variable name to search for

        Returns:
            Tuple of (min, max) or None if not found
        """
        if not constraint_str or not variable:
            return None

        # Search for patterns like "1 ≤ n ≤ 100"
        pattern = rf"(\d+)\s*(?:≤|<=|<)\s*{variable}\s*(?:≤|<=|<)\s*(\d+)"
        match = re.search(pattern, constraint_str, re.IGNORECASE)

        if match:
            min_val = int(match.group(1))
            max_val = int(match.group(2))
            return (min_val, max_val)

        return None

    def validate_test_pair(self,
                          test_input: str,
                          test_output: str,
                          executable_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validate a test input/output pair. Optionally run against executable.

        Args:
            test_input: Test input string
            test_output: Expected test output string
            executable_path: Path to compiled executable (optional)

        Returns:
            Tuple of (is_valid, message)
        """
        # Check basic format
        if not test_input or not isinstance(test_input, str):
            return False, "Invalid input format"

        if not test_output or not isinstance(test_output, str):
            return False, "Invalid output format"

        # Check lengths
        if len(test_input) > 1000000:
            return False, "Input too long"

        if len(test_output) > 100000:
            return False, "Output too long"

        return True, "Valid test case"

    def get_validation_summary(self, tests: List[Dict], constraints: Dict) -> Dict[str, Any]:
        """
        Get summary of test validation results.

        Args:
            tests: List of test cases
            constraints: Problem constraints

        Returns:
            Dict with validation statistics
        """
        if not tests:
            return {
                "total_tests": 0,
                "valid_tests": 0,
                "invalid_tests": 0,
                "pass_rate": 0.0,
                "issues": ["No tests provided"]
            }

        valid_count = sum(1 for test in tests if self.validate(test, constraints))
        invalid_count = len(tests) - valid_count

        return {
            "total_tests": len(tests),
            "valid_tests": valid_count,
            "invalid_tests": invalid_count,
            "pass_rate": valid_count / len(tests) if tests else 0.0,
            "issues": [] if invalid_count == 0 else ["Some test cases failed validation"]
        }

