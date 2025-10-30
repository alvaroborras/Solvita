"""Test Case Generator - LangGraph Compatible

Generates comprehensive test cases for competitive programming problems.
Returns state-compatible test case structures.
"""

import random
from typing import Dict, List, Any
from loguru import logger


class TestGenerator:
    """Generate test cases based on problem constraints and requirements"""

    def __init__(self, llm):
        """
        Initialize test generator.

        Args:
            llm: LLM instance for intelligent test generation
        """
        self.llm = llm

    def generate(self,
                constraints: Dict,
                problem_types: List[str],
                public_tests: List[Dict],
                num_tests: int = 20) -> Dict[str, Any]:
        """
        Generate comprehensive test suite.

        Args:
            constraints: Problem constraints
            problem_types: Problem type tags
            public_tests: Existing public test cases
            num_tests: Total number of tests to generate

        Returns:
            Dict with test fields for SolvitaState:
            - generated_tests: All tests combined
            - edge_cases: Boundary value tests
            - corner_cases: Special pattern tests
            - random_cases: Random valid tests
            - test_coverage_stats: Coverage metrics
        """
        logger.info(f"Generating {num_tests} test cases...")

        # Distribute test generation
        num_edge = int(num_tests * 0.3)
        num_corner = int(num_tests * 0.2)
        num_random = num_tests - num_edge - num_corner

        # Generate different types
        edge_cases = self.generate_edge_cases(constraints)[:num_edge]
        corner_cases = self.generate_corner_cases(constraints, problem_types)[:num_corner]
        random_cases = self.generate_random_cases(constraints, num_random)

        # Combine all tests
        all_tests = public_tests + edge_cases + corner_cases + random_cases

        # Calculate coverage stats
        stats = {
            "total": len(all_tests),
            "public": len(public_tests),
            "edge": len(edge_cases),
            "corner": len(corner_cases),
            "random": len(random_cases),
        }

        logger.info(f"Generated {len(all_tests)} total tests: {stats}")

        return {
            "generated_tests": all_tests,
            "edge_cases": edge_cases,
            "corner_cases": corner_cases,
            "random_cases": random_cases,
            "total_tests": len(all_tests),
            "test_coverage_stats": stats,
        }

    def generate_edge_cases(self, constraints: Dict) -> List[Dict]:
        """
        Generate boundary value test cases.

        Returns tests at min/max constraint boundaries.
        """
        edge_cases = []

        variables = constraints.get("variables", [])
        if not variables:
            return edge_cases

        # Test ID counter
        test_id = 1

        # Generate min/max combinations
        for var in variables:
            var_name = var["name"]
            var_min = var.get("min", 1)
            var_max = var.get("max", 100)

            # Minimum value test
            edge_cases.append({
                "id": f"edge_{test_id}",
                "input": str(var_min),
                "expected_output": None,
                "category": "edge_case",
                "description": f"Minimum value for {var_name}",
                "constraints_satisfied": True,
                "metadata": {
                    "generated_by": "rule_based",
                    "complexity": "simple",
                    "coverage_target": "min_value",
                },
            })
            test_id += 1

            # Maximum value test
            edge_cases.append({
                "id": f"edge_{test_id}",
                "input": str(var_max),
                "expected_output": None,
                "category": "edge_case",
                "description": f"Maximum value for {var_name}",
                "constraints_satisfied": True,
                "metadata": {
                    "generated_by": "rule_based",
                    "complexity": "hard",
                    "coverage_target": "max_value",
                },
            })
            test_id += 1

        logger.debug(f"Generated {len(edge_cases)} edge cases")
        return edge_cases

    def generate_corner_cases(self,
                             constraints: Dict,
                             problem_types: List[str]) -> List[Dict]:
        """
        Generate special corner case tests.

        Returns tests for special patterns based on problem type.
        """
        corner_cases = []
        test_id = 1

        # Type-specific corner cases
        if "array" in problem_types:
            corner_cases.extend([
                {
                    "id": f"corner_{test_id}",
                    "input": "0",  # Empty array
                    "expected_output": None,
                    "category": "corner_case",
                    "description": "Empty array",
                    "constraints_satisfied": True,
                    "metadata": {
                        "generated_by": "rule_based",
                        "complexity": "simple",
                        "coverage_target": "empty",
                    },
                },
            ])
            test_id += 1

        if "string" in problem_types:
            corner_cases.append({
                "id": f"corner_{test_id}",
                "input": "",  # Empty string
                "expected_output": None,
                "category": "corner_case",
                "description": "Empty string",
                "constraints_satisfied": True,
                "metadata": {
                    "generated_by": "rule_based",
                    "complexity": "simple",
                    "coverage_target": "empty",
                },
            })
            test_id += 1

        logger.debug(f"Generated {len(corner_cases)} corner cases")
        return corner_cases

    def generate_random_cases(self,
                             constraints: Dict,
                             num_cases: int) -> List[Dict]:
        """
        Generate random valid test cases.

        Returns randomly generated tests within constraints.
        """
        random_cases = []

        variables = constraints.get("variables", [])
        if not variables:
            # Generate simple random numbers
            for i in range(num_cases):
                random_cases.append({
                    "id": f"random_{i+1}",
                    "input": str(random.randint(1, 100)),
                    "expected_output": None,
                    "category": "random",
                    "description": f"Random test case {i+1}",
                    "constraints_satisfied": True,
                    "metadata": {
                        "generated_by": "rule_based",
                        "complexity": "medium",
                        "coverage_target": "typical",
                    },
                })
            return random_cases

        # Generate based on constraints
        for i in range(num_cases):
            # Pick random values within constraints
            test_values = []
            for var in variables:
                var_min = var.get("min", 1)
                var_max = var.get("max", 100)
                random_val = random.randint(var_min, var_max)
                test_values.append(str(random_val))

            random_cases.append({
                "id": f"random_{i+1}",
                "input": "\n".join(test_values),
                "expected_output": None,
                "category": "random",
                "description": f"Random test case {i+1}",
                "constraints_satisfied": True,
                "metadata": {
                    "generated_by": "rule_based",
                    "complexity": "medium",
                    "coverage_target": "typical",
                },
            })

        logger.debug(f"Generated {len(random_cases)} random cases")
        return random_cases

