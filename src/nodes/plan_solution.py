"""Plan Solution Node - Generate solution approach"""

from typing import Dict, Any, TYPE_CHECKING
import json
from loguru import logger
from src.llm import UnifiedLLMClient

if TYPE_CHECKING:
    from src.graph.state import SolvitaState, PlanData


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks

    Supports:
    - Pure JSON: {"key": "value"}
    - Markdown wrapped: ```json\n{"key": "value"}\n```
    - Generic code block: ```\n{"key": "value"}\n```
    """
    cleaned = response.strip()

    # Remove markdown code block markers
    if '```json' in cleaned:
        # Extract content between ```json and ```
        parts = cleaned.split('```json')
        if len(parts) > 1:
            cleaned = parts[1].split('```')[0].strip()
    elif '```' in cleaned:
        # Extract content between ``` and ```
        parts = cleaned.split('```')
        if len(parts) >= 3:
            cleaned = parts[1].strip()

    # Parse JSON
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response content: {cleaned[:200]}...")
        raise


def plan_solution_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Plan solution approach using LLM

    Generates:
    - Algorithm choice
    - Implementation steps
    - Solution plan with key insights
    """
    logger.info("[Node] Planning solution approach")

    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])

    # Build planning prompt
    problem_desc = state['problem'].get('description', '')
    problem_types = state['problem'].get('types', [])
    constraints = state['problem'].get('constraints', {})

    prompt = f"""Analyze this competitive programming problem and design an optimal solution.

Problem Description:
{problem_desc}

Problem Types: {', '.join(problem_types) if problem_types else 'Not specified'}
Constraints: {constraints}

Please provide a detailed solution plan in JSON format:

{{
  "algorithm_choice": "Name of the algorithm or approach (e.g., 'Two Pointers', 'Dynamic Programming', 'Binary Search')",
  "implementation_steps": [
    "Step 1: Description of first step",
    "Step 2: Description of second step",
    "Step 3: Description of third step"
  ],
  "key_insights": "Why this approach works and handles edge cases",
  "time_complexity": "O(...)",
  "space_complexity": "O(...)"
}}

Requirements:
- Focus on correctness and efficiency
- Consider edge cases
- Provide clear, actionable steps

Return ONLY the JSON object, no additional text."""

    # Get planning response from LLM
    response = llm.generate(prompt)

    # Parse JSON response
    try:
        plan_data = parse_json_response(response)

        algorithm_choice = plan_data.get('algorithm_choice', 'Unknown algorithm')
        implementation_steps = plan_data.get('implementation_steps', [])

        logger.info(f"Algorithm chosen: {algorithm_choice}")
        logger.info(f"Implementation steps: {len(implementation_steps)}")

    except json.JSONDecodeError:
        # If parsing fails, use defaults
        logger.warning("Failed to parse plan response, using defaults")
        algorithm_choice = "General approach"
        implementation_steps = ["Analyze problem", "Implement solution", "Test edge cases"]
        plan_data = {'response': response}

    # Create plan dict (avoiding PlanData import for circular dep fix)
    plan = {
        "solution_plan": plan_data,
        "algorithm_choice": algorithm_choice,
        "implementation_steps": implementation_steps,
    }

    return {
        "plan": plan,
        "execution_log": [
            f"✓ Solution plan generated: {algorithm_choice}",
            f"  Implementation steps: {len(implementation_steps)}"
        ],
        "llm_calls": 1,
    }

