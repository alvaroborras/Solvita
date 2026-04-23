"""Routing Functions - Conditional edge routing logic"""

from typing import Dict, Any


def _hacker_enabled(state: Dict[str, Any]) -> bool:
    config = (state.get("config", {}) or {})
    workflow = (config.get("workflow", {}) or {}) if isinstance(config, dict) else {}
    if "hacker_enabled" in workflow:
        return bool(workflow.get("hacker_enabled", True))
    return bool(config.get("hacker_enabled", True))


def status_routing(state: Dict[str, Any]) -> str:
    """
    Routing after memory settlement.

    Returns:
      - "hack": if status == "success" and hacker is enabled
      - "finish": if status == "success" and hacker is disabled
      - "continue": if still iterating
      - "end": if max_iterations reached (give up)
    """
    status = state.get("status", "pending")

    if status == "success":
        return "hack" if _hacker_enabled(state) else "finish"
    elif status == "max_iterations":
        return "end"
    else:
        return "continue"


def post_codegen_routing(state: Dict[str, Any]) -> str:
    status = state.get("status", "pending")
    if status == "success" and _hacker_enabled(state):
        return "to_hacker"
    return "end"


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
    # If adversarial input generation failed entirely, do not spin the inner hack loop.
    # The node still reports hack_passed=True (no successful break), but we should settle and exit.
    if str(state.get("hack_result", "") or "").upper() == "GEN_FAILED":
        return "end"

    if state.get("hack_passed", False):
        hack_round = state.get("hack_round", 0)
        max_rounds = state.get("max_hack_rounds", 3)
        if hack_round >= max_rounds:
            return "end"
        return "hack_again"
    return "hack_failed"


def hack_outcome_routing(state: Dict[str, Any]) -> str:
    """
    Top-level routing AFTER the entire hacker_phase subgraph exits.

    - "loop_codegen": hack found bugs (hack_passed=False) -> send solution
                      back to CodeGen with hack failures as additional tests
    - "final_ac":     hack exhausted all rounds without finding bugs ->
                      solution is robust, declare Final AC
    """
    hack_passed = state.get("hack_passed", True)
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 5)

    if not hack_passed:
        if iteration < max_iterations:
            return "loop_codegen"
        return "terminal_failure"
    return "final_ac"


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
