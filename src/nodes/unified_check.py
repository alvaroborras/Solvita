"""Unified Check Node - Check solution status and decide next step"""

from typing import Dict, Any
from loguru import logger
from src.graph.state import SolvitaState


def unified_check_node(state: SolvitaState) -> Dict[str, Any]:
    """
    Unified check node that determines solution status and iteration control
    
    Checks:
    1. Are all tests passing? → success
    2. Have we reached max iterations? → max_iterations
    3. Otherwise → continue iteration
    """
    logger.info(f"[Node] Unified check (iteration {state['iteration']})")
    
    # Check 1: Are all tests passing?
    all_passed = (
        state['solution'].get('compilation_success', False)
        and state['tests'].get('total_tests', 0) > 0
        and state['tests'].get('pass_rate', 0.0) >= 1.0
    )
    
    if all_passed:
        return {
            "status": "success",
            "execution_log": ["✓ All tests passed! Solution complete."],
        }
    
    # Check 2: Have we reached max iterations?
    if state["iteration"] >= state["max_iterations"]:
        return {
            "status": "max_iterations",
            "execution_log": [
                f"✗ Max iterations ({state['max_iterations']}) reached"
            ],
        }
    
    # Check 3: Continue iteration
    passed = state['tests'].get('passed_tests', 0)
    total = state['tests'].get('total_tests', 0)
    
    return {
        "iteration": state["iteration"] + 1,
        "execution_log": [
            f"Tests status: {passed}/{total} passed",
            f"→ Starting iteration {state['iteration'] + 1}",
        ],
    }

