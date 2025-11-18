"""Plan Solution Node - Generate solution approach"""

from typing import Dict, Any
from loguru import logger
from src.graph.state import SolvitaState, PlanData
from src.llm import UnifiedLLMClient


def plan_solution_node(state: SolvitaState) -> Dict[str, Any]:
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
    
    prompt = f"""Design an optimal solution for this competitive programming problem:

Problem: {problem_desc}

Problem Types: {', '.join(problem_types)}
Constraints: {constraints}

Provide:
1. Algorithm choice (which algorithm/data structure to use)
2. Implementation steps (step-by-step approach)
3. Key insights (why this approach works)

Format your response as a structured plan."""
    
    # Get planning response from LLM
    response = llm.generate(prompt)
    
    # Store complete response
    plan = PlanData(
        solution_plan={'response': response},
        algorithm_choice='',  # LLM will provide in response
        implementation_steps=[],  # LLM will provide in response
    )
    
    return {
        "plan": plan,
        "execution_log": ["✓ Solution plan generated"],
        "llm_calls": state['llm_calls'] + 1,
    }

