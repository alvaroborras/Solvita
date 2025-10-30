"""Problem Parser - LangGraph Compatible

This module parses raw problem input and extracts structured information.
All methods work with SolvitaState or return state-compatible dictionaries.
"""

import re
from typing import Dict, List, Any, Optional
from loguru import logger


class ProblemParser:
    """Parse competitive programming problems into structured format"""

    def __init__(self, llm=None):
        """
        Initialize problem parser.

        Args:
            llm: Optional LLM for enhanced parsing (can use rule-based if None)
        """
        self.llm = llm

    def parse(self, raw_problem: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse raw problem into structured format.

        Args:
            raw_problem: Dict with 'description' and optionally 'public_tests'

        Returns:
            Dictionary with parsed fields compatible with SolvitaState
        """
        logger.info("Parsing problem...")

        description = raw_problem.get("description", "")
        raw_tests = raw_problem.get("public_tests", [])

        # Extract components
        constraints = self.extract_constraints(description)
        input_format = self.extract_input_format(description)
        output_format = self.extract_output_format(description)
        problem_types = self.identify_problem_types(description)
        difficulty = self.estimate_difficulty(description, constraints)
        time_limit, memory_limit = self.extract_limits(raw_problem)

        # Parse public tests
        public_tests = self.parse_public_tests(raw_tests)

        return {
            "problem_description": description,
            "public_tests": public_tests,
            "constraints": constraints,
            "input_format": input_format,
            "output_format": output_format,
            "problem_types": problem_types,
            "difficulty": difficulty,
            "time_limit": time_limit,
            "memory_limit": memory_limit,
        }

    def extract_constraints(self, description: str) -> Dict[str, Any]:
        """
        Extract constraints from problem description.

        Returns:
            Dict with 'variables' list and other constraint info
        """
        # TODO: Implement full constraint extraction with LLM
        constraints = {
            "variables": [],
            "special_constraints": [],
        }

        # Simple regex-based extraction (placeholder)
        constraint_pattern = r'(\d+)\s*[≤<=]+\s*([a-zA-Z_]\w*)\s*[≤<=]+\s*(\d+(?:\^\d+)?)'
        matches = re.findall(constraint_pattern, description)

        for match in matches:
            min_val, var_name, max_val = match
            constraints["variables"].append({
                "name": var_name,
                "type": "int",
                "min": self._parse_value(min_val),
                "max": self._parse_value(max_val),
            })

        logger.debug(f"Extracted {len(constraints['variables'])} constraint variables")
        return constraints

    def extract_input_format(self, description: str) -> Dict[str, Any]:
        """Extract input format description"""
        # TODO: Parse input format from description
        return {
            "description": "To be parsed from problem description",
            "lines": [],
        }

    def extract_output_format(self, description: str) -> Dict[str, Any]:
        """Extract output format description"""
        # TODO: Parse output format from description
        return {
            "description": "To be parsed from problem description",
        }

    def identify_problem_types(self, description: str) -> List[str]:
        """
        Identify problem types/tags based on keywords.

        Returns:
            List of tags: ["dp", "graph", "greedy", etc.]
        """
        types = []
        keywords_map = {
            "dp": ["dynamic programming", "dp", "optimal substructure", "memoization"],
            "graph": ["graph", "tree", "node", "edge", "path", "cycle"],
            "greedy": ["greedy", "optimal choice", "local optimum"],
            "array": ["array", "sequence", "list"],
            "string": ["string", "substring", "character"],
            "math": ["mathematical", "formula", "prime", "gcd", "lcm"],
            "sorting": ["sort", "sorted", "ordering"],
            "binary_search": ["binary search", "sorted array"],
        }

        desc_lower = description.lower()
        for tag, keywords in keywords_map.items():
            if any(keyword in desc_lower for keyword in keywords):
                types.append(tag)

        return types if types else ["general"]

    def estimate_difficulty(self, description: str, constraints: Dict) -> str:
        """Estimate problem difficulty"""
        num_variables = len(constraints.get("variables", []))
        if num_variables <= 2:
            return "easy"
        elif num_variables <= 4:
            return "medium"
        else:
            return "hard"

    def extract_limits(self, raw_problem: Dict) -> tuple:
        """Extract time and memory limits"""
        time_limit = raw_problem.get("time_limit", 2000)
        memory_limit = raw_problem.get("memory_limit", 256)
        return time_limit, memory_limit

    def parse_public_tests(self, raw_tests: List[Dict]) -> List[Dict]:
        """Parse public test cases into standardized format"""
        parsed_tests = []
        for i, test in enumerate(raw_tests):
            parsed_tests.append({
                "id": f"public_{i+1}",
                "input": test.get("input", ""),
                "expected_output": test.get("output", ""),
                "category": "public",
                "description": f"Public test case {i+1}",
                "constraints_satisfied": True,
                "metadata": {
                    "generated_by": "problem_statement",
                    "complexity": "simple",
                    "coverage_target": "basic",
                },
            })
        logger.info(f"Parsed {len(parsed_tests)} public test cases")
        return parsed_tests

    def _parse_value(self, value_str: str) -> int:
        """Parse constraint value (handles 10^5 notation)"""
        if "^" in value_str:
            base, exp = value_str.split("^")
            return int(base) ** int(exp)
        return int(value_str)

