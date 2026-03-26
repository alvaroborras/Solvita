"""Plan Solution Node - Generate solution approach with trainable memory injection"""

from typing import Dict, Any, TYPE_CHECKING
import json
from loguru import logger
from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.memory import MemoryClient, MemoryNamespace
from src.utils.json_utils import parse_json_response
from src.utils.prompt_utils import compact_json_for_prompt, truncate_for_prompt

if TYPE_CHECKING:
    from src.graph.state import SolvitaState, PlanData


def build_plan_prompt(
    problem_desc: str,
    problem_types: list[str],
    constraints: Dict[str, Any],
    advice: str,
    compact: bool = False,
) -> str:
    desc_chars = 12000 if not compact else 6000
    constraint_chars = 3000 if not compact else 1500
    advice_chars = 4000 if not compact else 1500
    compact_problem_desc = truncate_for_prompt(problem_desc, desc_chars, "PROBLEM_DESC")
    compact_constraints = compact_json_for_prompt(constraints, constraint_chars, "CONSTRAINTS")
    advice_block = ""
    if advice:
        advice_block = f"\n{truncate_for_prompt(advice, advice_chars, 'PLAN_MEMORY_ADVICE')}\n"

    return f"""Analyze this competitive programming problem. You must produce TWO outputs:
1. A canonical problem representation (removing natural language ambiguity, using mathematical/algorithmic language)
2. A solution plan

Original Problem Description:
{compact_problem_desc}

Problem Types: {', '.join(problem_types[:8]) if problem_types else 'Not specified'}
Constraints: {compact_constraints}
{advice_block}
Return a single JSON object with these two sections:

{{
  "canonical_problem": {{
    "objective": "Precise mathematical/algorithmic statement of what to compute or decide",
    "inputs": {{
      "format": "Input format description",
      "variables": {{"n": "meaning", "arr": "meaning", ...}},
      "types": {{"n": "int", "arr": "list[int]", ...}}
    }},
    "outputs": {{
      "format": "Output format description",
      "variables": {{"result": "meaning"}},
      "types": {{"result": "int"}}
    }},
    "constraints": {{
      "normalized": {{"1 <= n <= 10^5": "size bound", "1 <= arr[i] <= 10^9": "value bound", ...}},
      "derived": ["Any implicit constraints or properties derived from the problem"]
    }},
    "required_properties": ["What the solution must satisfy (e.g., optimality, uniqueness, feasibility)"],
    "edge_cases": ["Minimal input (n=1)", "Maximum constraints", "Special values (0, negative, etc.)"]
  }},
  "plan": {{
    "algorithm_choice": "Name of the algorithm or approach (e.g., 'Two Pointers', 'Dynamic Programming', 'Binary Search')",
    "implementation_steps": [
      "Step 1: Description of first step",
      "Step 2: Description of second step",
      "Step 3: Description of third step"
    ],
    "data_structures": ["List of key data structures to use"],
    "corner_cases": ["Corner case 1", "Corner case 2"],
    "key_insights": "Why this approach works and handles edge cases",
    "time_complexity": "O(...)",
    "space_complexity": "O(...)"
  }}
}}

Requirements:
- The canonical_problem MUST be self-contained and precise (no narrative fluff)
- Focus on correctness and efficiency in the plan
- Verify your chosen algorithm fits within the time/space limits

Return ONLY the JSON object, no additional text."""


def plan_solution_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Plan solution approach using LLM with trainable memory injection.

    Generates:
    - Algorithm choice
    - Implementation steps
    - Solution plan with key insights

    The plan-agent trainable memory system injects Top-K planning strategies
    into the prompt to guide the LLM toward better algorithm selection and
    edge-case awareness.  Selected strategy IDs are stored in state so that
    downstream nodes can settle rewards after evaluation.
    """
    logger.info("[Node] Planning solution approach")

    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])

    # Initialize plan memory
    problem_desc = state['problem'].get('description', '')
    canonical = state['problem'].get('canonical', {})
    iteration = state.get('iteration', 0)
    
    memory = MemoryClient(
        namespace=MemoryNamespace.PLAN,
        config=state['config'],
        problem_desc=problem_desc,
        canonical=canonical,
    )

    # Determine failure context for replanning
    failure_type = None
    if iteration > 0:
        feedback_data = state.get('feedback', {}).get('feedback', {})
        error_pattern = feedback_data.get('error_pattern', '')
        if 'tle' in error_pattern.lower() or 'timeout' in error_pattern.lower():
            failure_type = 'TIMEOUT'
        elif 'compile' in error_pattern.lower():
            failure_type = 'COMPILE_FAIL'
        elif error_pattern:
            failure_type = 'SOLVE_WA'

    # Retrieve planning advice from trainable memory
    advice, memory_item_ids = memory.get_injection(
        fsm_state="SOLVE_DRAFT",
        failure_type=failure_type,
        attempt_count=iteration,
    )

    # Build planning prompt
    problem_types = state['problem'].get('types', [])
    constraints = state['problem'].get('constraints', {})

    prompt = build_plan_prompt(problem_desc, problem_types, constraints, advice, compact=False)

    # Get planning response from LLM (retry once on JSON parse failure)
    llm_calls = 0
    plan_data = None
    prompt_compact = False
    for attempt in range(2):
        try:
            response = llm.generate(prompt)
        except PromptTooLongError:
            if prompt_compact:
                raise
            prompt = build_plan_prompt(problem_desc, problem_types, constraints, advice, compact=True)
            prompt_compact = True
            logger.warning("Plan prompt exceeded max tokens, retrying with compact prompt")
            continue
        llm_calls += 1

        try:
            plan_data = parse_json_response(response)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                logger.warning("Plan JSON parse failed, retrying...")
            else:
                logger.warning("Plan JSON parse failed twice, using defaults")

    # Extract canonical problem and plan from response
    canonical_problem = {}
    if plan_data:
        canonical_problem = plan_data.get('canonical_problem', {})
        plan_section = plan_data.get('plan', {})
        algorithm_choice = plan_section.get('algorithm_choice', 'Unknown algorithm')
        implementation_steps = plan_section.get('implementation_steps', [])
    else:
        algorithm_choice = "General approach"
        implementation_steps = [
            "Analyze problem",
            "Implement solution",
            "Test edge cases",
        ]
        plan_section = {'response': response}

    logger.info(f"Algorithm chosen: {algorithm_choice}")
    logger.info(f"Implementation steps: {len(implementation_steps)}")
    logger.info(f"Canonical problem generated: {len(canonical_problem)} fields")

    # Create plan dict with memory tracking fields
    plan = {
        "solution_plan": plan_section,
        "algorithm_choice": algorithm_choice,
        "implementation_steps": implementation_steps,
        "memory_item_ids": memory_item_ids,
        "memory_advice": advice.strip() if advice else "",
    }

    return {
        "problem": {
            "canonical": canonical_problem,
        },
        "plan": plan,
        "execution_log": [
            f"✓ Solution plan generated: {algorithm_choice}",
            f"  Canonical problem: {len(canonical_problem)} fields",
            f"  Implementation steps: {len(implementation_steps)}",
            f"  Memory items injected: {len(memory_item_ids)}",
        ],
        "llm_calls": llm_calls,
    }
