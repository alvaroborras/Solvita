"""Update Oracle Memory Node - Settle rewards for oracle memory.

This node reads the item IDs that generate_tests_node stored in
state['oracle_memory_item_ids'] and sends a final reward signal to the
oracle-agent trainable memory system based on whether the Oracle generated
valid outputs or TLE'd successfully.
"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

from src.memory import MemoryClient, MemoryNamespace, Observation

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

def _compute_oracle_reward(state: Dict[str, Any]) -> float:
    """
    Compute reward for oracle memory items.
    High pass rate = Generated tests are valid and constraints hold = High Reward
    """
    status = state.get("status", "pending")
    if status == "success":
        return 1.0
    elif status in ("max_iterations", "error"):
        return -1.0
    else:
        pass_rate = state.get("tests", {}).get("pass_rate", 0.0)
        return pass_rate * 2.0 - 1.0


def _infer_oracle_failure_type(state: Dict[str, Any]) -> str:
    """Infer failure type from state for policy context."""
    pass_rate = state.get("tests", {}).get("pass_rate", 0.0)
    total_tests = state.get("tests", {}).get("total_tests", 0)

    if total_tests == 0:
        return "NO_TESTS"

    test_results = state.get("tests", {}).get("test_results", [])
    if any(r.get("error") == "Timeout" for r in test_results):
        return "TLE"
    if pass_rate == 0.0:
        return "ALL_FAIL"
    if pass_rate < 1.0:
        return "PARTIAL_FAIL"

    return ""


def update_oracle_memory_node(state: "SolvitaState") -> Dict[str, Any]:
    """Settle rewards for oracle-agent memory items."""
    item_ids = state.get("oracle_memory_item_ids", [])

    if not item_ids:
        logger.debug("[Node] update_oracle_memory: no item IDs to update")
        return {
            "execution_log": ["Oracle memory: no items to update"],
        }

    reward = _compute_oracle_reward(state)
    failure_type = _infer_oracle_failure_type(state) if reward < 1.0 else None
    iteration = state.get("iteration", 0)

    logger.info(
        f"[Node] Updating oracle memory: reward={reward:.2f}, "
        f"items={len(item_ids)}, failure_type={failure_type}"
    )

    problem_desc = state.get("problem", {}).get("description", "")
    canonical = state.get("problem", {}).get("canonical", {})

    memory = MemoryClient(
        namespace=MemoryNamespace.ORACLE,
        config=state["config"],
        problem_desc=problem_desc,
        canonical=canonical,
    )

    obs = Observation(
        fsm_state="ORACLE_SETTLE",
        failure_type=failure_type,
        attempt_count=iteration,
        canonical=canonical,
        raw_problem_desc=problem_desc,
    )

    if memory.featurizer:
        obs.feature_keys = memory.featurizer.extract_features(obs, MemoryNamespace.ORACLE)

    memory.log_event(obs, item_ids, reward, iteration=iteration)

    return {
        "execution_log": [
            f"Oracle memory updated: reward={reward:.2f} for "
            f"{len(item_ids)} items"
        ],
    }
