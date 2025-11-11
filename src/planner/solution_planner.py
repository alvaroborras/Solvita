"""Solution Planner - LangGraph Compatible

Plans solution approaches based on problem analysis and retrieved knowledge using LLM.
Returns state-compatible dictionaries.
"""

import json
from typing import Dict, List, Any
from loguru import logger


class SolutionPlanner:
    """Plan solution approaches for competitive programming problems using LLM"""

    def __init__(self, llm):
        """
        Initialize solution planner.

        Args:
            llm: LLM instance for generating plans
        """
        self.llm = llm
        if not llm:
            raise ValueError("SolutionPlanner requires an LLM instance")

    def plan(self,
             problem_description: str,
             problem_types: List[str],
             constraints: Dict,
             retrieved_knowledge: List[Dict]) -> Dict[str, Any]:
        """
        Create solution plan based on problem and knowledge using LLM.

        Args:
            problem_description: Problem text
            problem_types: Problem tags/types
            constraints: Problem constraints
            retrieved_knowledge: Retrieved similar problems and algorithms

        Returns:
            Dict with plan fields for SolvitaState:
            - solution_plan: Overall strategy with key insights
            - algorithm_choice: Selected algorithm
            - implementation_steps: Detailed step-by-step plan
        """
        logger.info("Planning solution approach using LLM...")

        try:
            # Build prompt for LLM
            planning_prompt = self._build_planning_prompt(
                problem_description,
                problem_types,
                constraints,
                retrieved_knowledge
            )

            # Call LLM to generate plan
            messages = [
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": planning_prompt
                }
            ]

            response = self.llm.chat(messages)

            # Parse LLM response
            plan_data = self._parse_planning_response(response)

            logger.debug(f"Generated plan with algorithm: {plan_data.get('algorithm_choice')}")
            return plan_data

        except Exception as e:
            logger.warning(f"LLM planning failed: {e}, falling back to heuristic approach")
            return self._generate_fallback_plan(problem_types, constraints)

    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM"""
        return """You are an expert algorithm designer for competitive programming problems.
Your task is to analyze a problem and design an optimal solution approach.

Respond ONLY with valid JSON in this exact format (no extra text before or after):
{
    "algorithm_choice": "Name of the selected algorithm",
    "implementation_steps": [
        "Step 1: ...",
        "Step 2: ...",
        "Step 3: ...",
        "..."
    ],
    "solution_plan": {
        "algorithm": "Algorithm name",
        "approach": "Brief description of the approach",
        "key_insights": [
            "Key insight 1",
            "Key insight 2",
            "..."
        ]
    }
}

Important:
- Return ONLY the JSON, no markdown, no explanations
- algorithm_choice must be a clear, concise algorithm name
- implementation_steps should be 4-6 detailed, actionable steps
- key_insights should explain why this algorithm is optimal for this problem
"""

    def _build_planning_prompt(self,
                               problem_description: str,
                               problem_types: List[str],
                               constraints: Dict,
                               retrieved_knowledge: List[Dict]) -> str:
        """Build user prompt for LLM"""

        constraints_text = self._format_constraints(constraints)
        knowledge_text = self._format_retrieved_knowledge(retrieved_knowledge)
        types_text = ", ".join(problem_types) if problem_types else "general"

        prompt = f"""Analyze this competitive programming problem and design an optimal solution:

**Problem Description:**
{problem_description}

**Problem Types:** {types_text}

**Constraints:**
{constraints_text}

**Retrieved Similar Problems/Algorithms:**
{knowledge_text}

Design an optimal solution using the format specified in the system prompt. Choose the algorithm that gives the best time and space complexity for these constraints."""

        return prompt

    def _format_constraints(self, constraints: Dict) -> str:
        """Format constraints for display"""
        if not constraints or not constraints.get("variables"):
            return "No specific constraints provided"

        lines = []
        for var in constraints.get("variables", []):
            name = var.get("name", "unknown")
            min_val = var.get("min", 1)
            max_val = var.get("max", 100)
            lines.append(f"- {name}: {min_val} to {max_val}")

        return "\n".join(lines) if lines else "No specific constraints"

    def _format_retrieved_knowledge(self, knowledge: List[Dict]) -> str:
        """Format retrieved knowledge for display"""
        if not knowledge:
            return "No similar problems found"

        lines = []
        for item in knowledge[:3]:  # Limit to top 3
            if isinstance(item, dict):
                prob_id = item.get("id", "unknown")
                algo = item.get("algorithm", "unknown")
                lines.append(f"- Problem {prob_id}: Uses {algo}")

        return "\n".join(lines) if lines else "No similar problems found"

    def _parse_planning_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM with fallback"""

        try:
            # Try to find JSON in response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                logger.warning("No JSON found in LLM response")
                return self._generate_minimal_plan()

            json_str = response[json_start:json_end]
            plan_data = json.loads(json_str)

            # Validate required fields
            required_fields = ['algorithm_choice', 'implementation_steps', 'solution_plan']
            if not all(field in plan_data for field in required_fields):
                logger.warning(f"Missing required fields in response: {plan_data.keys()}")
                return self._generate_minimal_plan()

            # Validate field types
            if not isinstance(plan_data['algorithm_choice'], str):
                logger.warning("algorithm_choice is not a string")
                return self._generate_minimal_plan()

            if not isinstance(plan_data['implementation_steps'], list):
                logger.warning("implementation_steps is not a list")
                return self._generate_minimal_plan()

            if not isinstance(plan_data['solution_plan'], dict):
                logger.warning("solution_plan is not a dict")
                return self._generate_minimal_plan()

            # Validate non-empty fields
            if not plan_data['algorithm_choice'].strip():
                logger.warning("algorithm_choice is empty")
                return self._generate_minimal_plan()

            if not plan_data['implementation_steps']:
                logger.warning("implementation_steps is empty")
                return self._generate_minimal_plan()

            # Ensure steps are strings
            steps = [str(step) for step in plan_data['implementation_steps']]

            return {
                "solution_plan": plan_data.get('solution_plan', {}),
                "algorithm_choice": plan_data['algorithm_choice'].strip(),
                "implementation_steps": steps,
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return self._generate_minimal_plan()
        except Exception as e:
            logger.warning(f"Unexpected error parsing response: {e}")
            return self._generate_minimal_plan()

    def _generate_minimal_plan(self) -> Dict[str, Any]:
        """Generate minimal fallback plan when parsing fails"""
        return {
            "solution_plan": {
                "algorithm": "General Approach",
                "approach": "Parse input, process, output result",
                "key_insights": ["Fallback plan due to parsing error"]
            },
            "algorithm_choice": "General Approach",
            "implementation_steps": [
                "1. Parse input according to problem format",
                "2. Process the input",
                "3. Output the result"
            ]
        }

    def _generate_fallback_plan(self,
                                problem_types: List[str],
                                constraints: Dict) -> Dict[str, Any]:
        """Generate fallback plan using heuristic approach"""

        algorithm = self._select_algorithm_heuristic(problem_types)
        steps = self._generate_steps_heuristic(algorithm)

        return {
            "solution_plan": {
                "algorithm": algorithm,
                "approach": f"Using {algorithm} approach",
                "key_insights": ["Fallback heuristic plan due to LLM error"]
            },
            "algorithm_choice": algorithm,
            "implementation_steps": steps,
        }

    def _select_algorithm_heuristic(self, problem_types: List[str]) -> str:
        """Select algorithm using heuristic rules"""
        algorithm_map = {
            "dp": "Dynamic Programming",
            "graph": "Graph Traversal (BFS/DFS)",
            "greedy": "Greedy Algorithm",
            "sorting": "Sorting",
            "binary_search": "Binary Search",
            "math": "Mathematical Formula",
            "two_pointers": "Two Pointers",
            "hash_map": "Hash Map",
        }

        for ptype in problem_types:
            if ptype in algorithm_map:
                return algorithm_map[ptype]

        return "Brute Force"

    def _generate_steps_heuristic(self, algorithm: str) -> List[str]:
        """Generate implementation steps using heuristic"""
        return [
            "1. Parse input according to problem format",
            f"2. Apply {algorithm} algorithm",
            "3. Handle edge cases",
            "4. Format and output result",
        ]

    def _select_algorithm(self,
                         problem_types: List[str],
                         knowledge: List[Dict]) -> str:
        """Select most appropriate algorithm (deprecated - kept for compatibility)"""
        return self._select_algorithm_heuristic(problem_types)

    def _generate_steps(self, algorithm: str, problem: str) -> List[str]:
        """Generate implementation steps (deprecated - kept for compatibility)"""
        return self._generate_steps_heuristic(algorithm)

    def estimate_complexity(self, algorithm: str, constraints: Dict) -> Dict[str, str]:
        """
        Estimate time and space complexity.

        Returns:
            Dict with 'time' and 'space' keys
        """
        if "Dynamic Programming" in algorithm:
            return {"time": "O(n^2)", "space": "O(n)"}
        elif "Graph" in algorithm:
            return {"time": "O(V + E)", "space": "O(V)"}
        elif "Sorting" in algorithm:
            return {"time": "O(n log n)", "space": "O(1)"}
        else:
            return {"time": "O(n)", "space": "O(1)"}

    def _identify_edge_cases(self,
                            constraints: Dict,
                            problem_types: List[str]) -> List[str]:
        """Identify edge cases to handle"""
        edge_cases = []

        # Add constraint-based edge cases
        if constraints.get("variables"):
            edge_cases.append("Minimum constraint values")
            edge_cases.append("Maximum constraint values")

        # Add type-specific edge cases
        if "array" in problem_types:
            edge_cases.extend([
                "Empty array",
                "Single element array",
                "All same elements",
            ])

        if "graph" in problem_types:
            edge_cases.extend([
                "Disconnected graph",
                "Single node",
            ])

        return edge_cases

