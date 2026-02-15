"""Join Ready Nodes - Coordinate compile/tests readiness before running tests"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _is_tests_ready(state: Dict[str, Any]) -> bool:
    tests = state.get("tests", {})
    return tests.get("ready", False) and bool(tests.get("generated_tests"))


def _is_compile_ready(state: Dict[str, Any]) -> bool:
    return state.get("solution", {}).get("compilation_success", False)


def join_ready_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Barrier node that only allows run_tests after both compile and tests are ready.
    """
    tests_ready = _is_tests_ready(state)
    compile_ready = _is_compile_ready(state)

    if not tests_ready or not compile_ready:
        logger.debug(
            f"[Join] Waiting: tests_ready={tests_ready}, compile_ready={compile_ready}"
        )
        updated_tests = dict(state.get("tests", {}))
        updated_tests["pending_execution"] = True
        return {
            "tests": updated_tests,
            "execution_log": ["Join waiting: tests/compilation not ready"],
        }

    logger.info("[Join] Ready: tests and compilation complete")
    return {
        "execution_log": ["Join ready: tests and compilation complete"],
    }


def join_wait_node(state: "SolvitaState") -> Dict[str, Any]:
    """No-op node used to end a join attempt when prerequisites are not ready."""
    return {
        "execution_log": ["Join wait: no action"],
    }
