"""Unified Check Node - Check solution status and decide next step"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def unified_check_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Unified check node that determines solution status and iteration control

    Checks:
    1. Are all tests passing? → success
    2. Have we reached max iterations? → max_iterations
    3. Otherwise → continue iteration
    """
    current_iteration = state.get('iteration', 0)
    max_iterations = state.get('max_iterations', 5)

    logger.info(f"[Node] Unified check (iteration {current_iteration}/{max_iterations})")

    if state.get('tests', {}).get('pending_execution', False):
        logger.debug("  Waiting for compilation/test generation; skipping unified decision")
        return {
            "status": state.get("status", "pending"),
            "execution_log": ["Waiting for compilation/test generation before unified check"],
        }

    # Check 1: Are all tests passing?
    compilation_success = state.get('solution', {}).get('compilation_success', False)
    total_tests = state.get('tests', {}).get('total_tests', 0)
    pass_rate = state.get('tests', {}).get('pass_rate', 0.0)

    logger.debug(f"  Compilation: {compilation_success}, Tests: {total_tests}, Pass rate: {pass_rate:.1%}")

    all_passed = compilation_success and total_tests > 0 and pass_rate >= 1.0

    if all_passed:
        logger.info("  → SUCCESS: All tests passed!")
        return {
            "status": "success",
            "execution_log": ["✓ All tests passed! Solution complete."],
        }

    # Check 2: Have we reached max iterations?
    if current_iteration >= max_iterations:
        logger.info(f"  → MAX_ITERATIONS: Reached {max_iterations}")
        return {
            "status": "max_iterations",
            "execution_log": [
                f"✗ Max iterations ({max_iterations}) reached"
            ],
        }

    # Check 3: Continue iteration
    passed = state.get('tests', {}).get('passed_tests', 0)
    total = state.get('tests', {}).get('total_tests', 0)
    next_iteration = current_iteration + 1

    logger.info(f"  → CONTINUE: {passed}/{total} passed, starting iteration {next_iteration}")

    return {
        "iteration": next_iteration,
        "status": "pending",  # Explicitly set status to pending
        "execution_log": [
            f"Tests status: {passed}/{total} passed",
            f"→ Starting iteration {next_iteration}",
        ],
    }

