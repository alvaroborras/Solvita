"""Routing Functions - Conditional edge routing logic"""

from src.graph.state import SolvitaState


def status_routing(state: SolvitaState) -> str:
    """
    Routing function based on solution status
    
    Returns:
    - "end": if success or max_iterations reached
    - "continue": if should continue iterating
    """
    status = state.get("status", "pending")
    
    if status == "success":
        return "end"
    elif status == "max_iterations":
        return "end"
    else:
        return "continue"


def compilation_routing(state: SolvitaState) -> str:
    """
    Routing function after compilation
    
    Returns:
    - "success": if compilation succeeded → go to run_tests
    - "failed": if compilation failed → go to analyze_feedback
    """
    if state['solution'].get('compilation_success', False):
        return "success"
    else:
        return "failed"

