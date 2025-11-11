"""C++ Code Generator - LangGraph Compatible

Generates C++ solution code based on plans and feedback using LLM.
"""

from typing import Dict, Optional, Any, List
from loguru import logger


class CPPGenerator:
    """Generate and refine C++ code solutions using LLM"""

    def __init__(self, llm):
        """
        Initialize C++ code generator.

        Args:
            llm: LLM instance for code generation
        """
        self.llm = llm
        if not llm:
            raise ValueError("CPPGenerator requires an LLM instance")

    def generate(self,
                problem_description: str,
                solution_plan: Dict,
                algorithm_choice: str,
                implementation_steps: List[str],
                feedback: Optional[Dict] = None) -> str:
        """
        Generate C++ solution code using LLM.

        Args:
            problem_description: Problem text
            solution_plan: Overall solution strategy
            algorithm_choice: Selected algorithm
            implementation_steps: Step-by-step plan
            feedback: Optional feedback for iteration

        Returns:
            C++ source code string
        """
        if feedback:
            # Refinement based on feedback
            logger.info(f"Refining C++ code based on feedback (attempt {feedback.get('attempt', 1)})...")
            return self._generate_with_feedback(
                problem_description,
                solution_plan,
                algorithm_choice,
                implementation_steps,
                feedback
            )
        else:
            # Initial code generation
            logger.info(f"Generating C++ code using {algorithm_choice}...")
            return self._generate_initial_code(
                problem_description,
                solution_plan,
                algorithm_choice,
                implementation_steps
            )

    def _generate_initial_code(self,
                               problem_description: str,
                               solution_plan: Dict,
                               algorithm_choice: str,
                               implementation_steps: List[str]) -> str:
        """Generate initial C++ code using LLM"""

        # Build the system prompt for code generation
        system_prompt = """You are an expert competitive programmer. Your task is to generate correct, efficient C++ code to solve programming problems.

Requirements:
1. The code must compile without errors
2. Follow competitive programming best practices
3. Handle input/output according to problem specifications
4. Use appropriate data structures and algorithms
5. Write clean, readable code with comments for complex parts
6. Include all necessary headers
7. Make sure the main() function reads input and prints output correctly"""

        # Build the user prompt with problem context
        steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(implementation_steps)])

        user_prompt = f"""Generate a complete C++ solution for the following problem:

**Problem Description:**
{problem_description}

**Selected Algorithm:** {algorithm_choice}

**Solution Strategy:**
{self._format_solution_plan(solution_plan)}

**Implementation Steps:**
{steps_text if implementation_steps else "No specific steps provided"}

**Requirements:**
- Complete, compilable C++ code
- Proper input/output handling
- Efficient implementation using {algorithm_choice}
- Clear variable names and comments

Please provide only the C++ code, starting with #include statements and ending with the closing brace of main()."""

        try:
            # Call LLM to generate code
            code = self.llm.generate_with_system(system_prompt, user_prompt)

            # Extract code if wrapped in markdown
            code = self._extract_code(code)

            logger.debug(f"Generated code ({len(code)} chars)")
            return code

        except Exception as e:
            logger.warning(f"LLM code generation failed: {e}, falling back to template")
            return self._generate_fallback_code(problem_description, algorithm_choice)

    def _generate_with_feedback(self,
                                problem_description: str,
                                solution_plan: Dict,
                                algorithm_choice: str,
                                implementation_steps: List[str],
                                feedback: Dict) -> str:
        """Refine code generation based on feedback"""

        compilation_errors = feedback.get('compilation_errors', [])
        test_failures = feedback.get('test_failures', [])
        suggestions = feedback.get('suggested_fixes', [])

        system_prompt = """You are an expert competitive programmer fixing compilation errors and test failures. Your task is to refine C++ code based on error feedback.

Focus on:
1. Fixing all compilation errors reported
2. Correcting logic errors causing test failures
3. Improving algorithmic correctness
4. Maintaining code efficiency
5. Ensuring proper input/output format"""

        feedback_text = ""
        if compilation_errors:
            feedback_text += f"**Compilation Errors:**\n" + "\n".join([f"- {err}" for err in compilation_errors[:3]])
        if test_failures:
            feedback_text += f"\n\n**Test Failures:**\n" + "\n".join([f"- {fail}" for fail in test_failures[:3]])
        if suggestions:
            feedback_text += f"\n\n**Suggested Fixes:**\n" + "\n".join([f"- {sug}" for sug in suggestions[:3]])

        user_prompt = f"""Fix the following C++ solution based on the feedback:

**Problem Description:**
{problem_description}

**Algorithm:** {algorithm_choice}

**Feedback to Address:**
{feedback_text}

**Guidelines:**
1. Fix all reported compilation errors
2. Address the test failures
3. Keep the same general approach unless it's fundamentally wrong
4. Maintain code clarity and efficiency

Please provide only the corrected C++ code."""

        try:
            code = self.llm.generate_with_system(system_prompt, user_prompt)
            code = self._extract_code(code)
            logger.debug(f"Refined code ({len(code)} chars)")
            return code

        except Exception as e:
            logger.warning(f"LLM refinement failed: {e}, returning fallback code")
            return self._generate_fallback_code(problem_description, algorithm_choice)

    def _extract_code(self, response: str) -> str:
        """Extract C++ code from LLM response (handle markdown wrapping)"""
        # If response contains markdown code blocks, extract the C++ code
        if "```cpp" in response:
            start = response.find("```cpp") + 6
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
        elif "```c++" in response:
            start = response.find("```c++") + 6
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        # If no markdown, return as-is
        return response.strip()

    def _format_solution_plan(self, solution_plan: Dict) -> str:
        """Format solution plan dictionary for prompt"""
        if not solution_plan:
            return "No specific plan provided"

        lines = []
        for key, value in solution_plan.items():
            if isinstance(value, (list, dict)):
                lines.append(f"- {key}: {str(value)[:100]}...")
            else:
                lines.append(f"- {key}: {value}")

        return "\n".join(lines) if lines else "No specific plan provided"

    def _generate_fallback_code(self, problem: str, algorithm: str) -> str:
        """Generate fallback template C++ code when LLM fails"""
        template = f"""#include <iostream>
#include <vector>
#include <algorithm>
#include <map>
#include <set>
using namespace std;

// Using {algorithm} approach
int main() {{
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);

    // Problem: {problem[:60]}
    // TODO: Implement solution

    int n;
    cin >> n;

    // Process input and solve

    // Output result
    cout << 0 << endl;

    return 0;
}}
"""
        return template

