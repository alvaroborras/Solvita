"""Routing Functions - Conditional edge routing logic"""

from typing import Dict, Any


def status_routing(state: Dict[str, Any]) -> str:
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


def compilation_routing(state: Dict[str, Any]) -> str:
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
