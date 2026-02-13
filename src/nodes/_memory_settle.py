"""Shared helper for memory settlement nodes.

Both update_plan_memory_node and update_solve_memory_node use
identical reward computation and failure inference logic. This
module factors that out into a single ``settle_memory`` function.
"""

from typing import Dict, Any, List, Optional, TYPE_CHECKING
from loguru import logger

from src.memory import MemoryClient, MemoryNamespace, Observation

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def compute_reward(state: Dict[str, Any]) -> float:
    """
    Compute reward based on workflow outcome.

    Returns:
        +1.0  : all tests passed (success)
        -1.0  : max_iterations or error
        else  : pass_rate - 0.5  (range [-0.5, +0.5])
    """
    status = state.get("status", "pending")
    if status == "success":
        return 1.0
    if status in ("max_iterations", "error"):
        return -1.0
    return state.get("tests", {}).get("pass_rate", 0.0) - 0.5


def infer_failure_type(state: Dict[str, Any]) -> str:
    """Infer failure type from state for policy context."""
    if not state.get("solution", {}).get("compilation_success", False):
        return "COMPILE_FAIL"
    pass_rate = state.get("tests", {}).get("pass_rate", 0.0)
    if pass_rate == 0.0:
        test_results = state.get("tests", {}).get("test_results", [])
        if any(r.get("error") == "Timeout" for r in test_results):
            return "TIMEOUT"
        return "SOLVE_WA"
    if pass_rate < 1.0:
        return "SOLVE_WA"
    return ""


def settle_memory(
    state: "SolvitaState",
    namespace: MemoryNamespace,
    item_ids: List[str],
    label: str,
) -> Dict[str, Any]:
    """
    Generic memory settlement: log event + update policy/stats.

    Args:
        state: Current workflow state.
        namespace: Which memory namespace to settle.
        item_ids: Item IDs selected during the injection phase.
        label: Human-readable label for logging (e.g. "Plan", "Solve").

    Returns:
        Partial state update (only execution_log).
    """
    if not item_ids:
        logger.debug(f"[Node] update_{label.lower()}_memory: no item IDs to update")
        return {"execution_log": [f"{label} memory: no items to update"]}

    reward = compute_reward(state)
    failure_type = infer_failure_type(state) if reward < 1.0 else None
    iteration = state.get("iteration", 0)

    logger.info(
        f"[Node] Updating {label.lower()} memory: reward={reward:.2f}, "
        f"items={len(item_ids)}, failure_type={failure_type}"
    )

    problem_desc = state.get("problem", {}).get("description", "")
    canonical = state.get("problem", {}).get("canonical", {})

    memory = MemoryClient(
        namespace=namespace,
        config=state["config"],
        problem_desc=problem_desc,
        canonical=canonical,
    )

    obs = Observation(
        fsm_state="SOLVE_CHECK",
        failure_type=failure_type,
        attempt_count=iteration,
        canonical=canonical,
        raw_problem_desc=problem_desc,
    )

    if memory.featurizer:
        obs.feature_keys = memory.featurizer.extract_features(obs, namespace)

    memory.log_event(obs, item_ids, reward, iteration=iteration)

    return {
        "execution_log": [
            f"{label} memory updated: reward={reward:.2f} for {len(item_ids)} items"
        ],
    }
