"""Generate Code Node - Generate C++ solution code"""

from typing import Dict, Any, Optional
from loguru import logger
from src.graph.state import SolvitaState, SolutionData
from src.llm import UnifiedLLMClient


def generate_code_node(state: SolvitaState) -> Dict[str, Any]:
    """
    Generate C++ solution code using LLM
    
    Uses:
    - Problem description
    - Solution plan
    - Previous feedback (if iteration > 0)
    """
    logger.info(f"[Node] Generating C++ code (version {state['solution'].get('version', 0) + 1})")
    
    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])
    
    problem_desc = state['problem'].get('description', '')
    algorithm = state['plan'].get('algorithm_choice', '')
    steps = state['plan'].get('implementation_steps', [])
    
    # Check if we have feedback from previous iteration
    feedback_text = ""
    if state['iteration'] > 0:
        feedback = state['feedback'].get('feedback', {})
        if feedback:
            feedback_text = f"\n\nPrevious attempt had issues:\n{feedback}\n\nPlease fix these issues."
    
    prompt = f"""Generate a complete C++ solution for this competitive programming problem:

Problem: {problem_desc}

Algorithm to use: {algorithm}

Implementation steps:
{chr(10).join(steps)}

{feedback_text}

Requirements:
- Use standard C++ (C++17)
- Include all necessary headers
- Implement fast I/O
- Handle all edge cases
- Optimize for time complexity

Generate ONLY the complete C++ code, no explanations."""
    
    code = llm.generate(prompt)
    
    # Simple cleanup: remove markdown code blocks if present
    code = code.strip()
    if code.startswith('```'):
        lines = code.split('\n')
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        code = '\n'.join(lines).strip()
    
    solution = SolutionData(
        code=code,
        version=state['solution'].get('version', 0) + 1,
        compilation_success=False,
        compilation_errors=[],
        executable_path=None,
    )
    
    return {
        "solution": solution,
        "execution_log": [f"✓ Generated C++ code (v{solution['version']})"],
        "llm_calls": state['llm_calls'] + 1,
    }

