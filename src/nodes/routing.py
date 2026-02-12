"""Routing Functions - Conditional edge routing logic"""

from typing import Dict, Any


def status_routing(state: Dict[str, Any]) -> str:
    """
    Routing function based on solution status
    
    Returns:
    - "success": if all tests passed → go to hack_test
    - "max_iterations": if max iterations reached → END
    - "continue": if should continue iterating
    """
    status = state.get("status", "pending")
    
    if status == "success":
        return "success"
    elif status == "max_iterations":
        return "max_iterations"
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

def hack_routing(state: Dict[str, Any]) -> str:
    """
    Routing function during Adversarial Hack Phase
    
    Returns:
    - "hack_again": if hack passed and rounds < max_rounds (continue hacking)
    - "end": if hack passed and rounds >= max_rounds (all clear)
    - "hack_failed": if hack found bugs (go to analyze_feedback)
    """
    if state.get("hack_passed", False):
        hack_round = state.get("hack_round", 0)
        max_rounds = state.get("max_hack_rounds", 3)
        if hack_round >= max_rounds:
            return "end"
        return "hack_again"
    return "hack_failed"
