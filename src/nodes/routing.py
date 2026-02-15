"""Routing Functions - Conditional edge routing logic"""

from typing import Dict, Any


def status_routing(state: Dict[str, Any]) -> str:
    """
    Routing after memory settlement.

    Returns:
      - "hack": if status == "success" -> enter adversarial hack phase
      - "continue": if still iterating
      - "end": if max_iterations reached (give up)
    """
    status = state.get("status", "pending")

    if status == "success":
        return "hack"
    elif status == "max_iterations":
        return "end"
    else:
        return "continue"


def compilation_routing(state: Dict[str, Any]) -> str:
    """
    Routing after compilation.

    Returns:
      - "success": compilation ok -> proceed to run_tests
      - "failed": compilation failed -> analyze_feedback
    """
    if state["solution"].get("compilation_success", False):
        return "success"
    return "failed"


def hack_routing(state: Dict[str, Any]) -> str:
    """
    Routing during the adversarial hack phase.

    Returns:
      - "hack_again": hack passed but rounds < max -> keep hacking
      - "end": hack passed and rounds >= max -> all clear, done
      - "hack_failed": hack found bugs -> analyze_feedback
    """
    if state.get("hack_passed", False):
        hack_round = state.get("hack_round", 0)
        max_rounds = state.get("max_hack_rounds", 3)
        if hack_round >= max_rounds:
            return "end"
        return "hack_again"
    return "hack_failed"


def join_routing(state: Dict[str, Any]) -> str:
        """
        Routing for the compile/tests join.

        Returns:
            - "ready": both compile and tests are ready
            - "wait": otherwise
        """
        tests = state.get("tests", {})
        tests_ready = tests.get("ready", False) and bool(tests.get("generated_tests"))
        compile_ready = state.get("solution", {}).get("compilation_success", False)

        if tests_ready and compile_ready:
                return "ready"
        return "wait"
