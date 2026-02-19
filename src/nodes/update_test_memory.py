"""Update Test Memory Node - Settle rewards for test memory after full workflow.

This node runs after the final outcome (success / failure / pass_rate) is
known. It reads the item IDs that generate_tests_node stored in
state['test_memory_item_ids'] and sends a final reward signal to the
test-agent trainable memory system.

The reward is computed from the overall workflow outcome (pass_rate),
allowing test-memory strategies to be refined based on end-to-end results.
"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

from src.memory import MemoryClient, MemoryNamespace, Observation

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _compute_test_reward(state: Dict[str, Any]) -> float:
    """
    Compute reward for test memory items based on workflow outcome.

    The test memory is rewarded based on how well the generated tests helped
    exercise the solution — proxied by the overall pass_rate.

    Reward scale:
        +1.0  : workflow succeeded (all tests passed)
        -1.0  : reached max_iterations or unrecoverable error
         else : pass_rate * 2.0 - 1.0  → maps [0%, 100%] → [-1.0, +1.0]
                so 100% → +1.0, 50% → 0.0, 0% → -1.0
    """
    status = state.get("status", "pending")

    if status == "success":
        return 1.0
    elif status in ("max_iterations", "error"):
        return -1.0
    else:
        pass_rate = state.get("tests", {}).get("pass_rate", 0.0)
        return pass_rate * 2.0 - 1.0


def _infer_test_failure_type(state: Dict[str, Any]) -> str:
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

    return ""  # No failure


def update_test_memory_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Settle rewards for test-agent memory items.

    This node is a pass-through for the workflow state — it does not modify
    any business-logic fields. It only updates the persistent test memory
    (policy weights + item stats + event log) as a side effect.

    Item IDs come from state['test_memory_item_ids'], which is populated by
    generate_tests_node at the time of memory injection.
    """
    item_ids = state.get("test_memory_item_ids", [])

    if not item_ids:
        logger.debug("[Node] update_test_memory: no item IDs to update")
        return {
            "execution_log": ["Test memory: no items to update"],
        }

    reward = _compute_test_reward(state)
    failure_type = _infer_test_failure_type(state) if reward < 1.0 else None
    iteration = state.get("iteration", 0)

    logger.info(
        f"[Node] Updating test memory: reward={reward:.2f}, "
        f"items={len(item_ids)}, failure_type={failure_type}"
    )

    problem_desc = state.get("problem", {}).get("description", "")
    canonical = state.get("problem", {}).get("canonical", {})

    memory = MemoryClient(
        namespace=MemoryNamespace.TEST,
        config=state["config"],
        problem_desc=problem_desc,
        canonical=canonical,
    )

    # Create observation for event logging (post-generation settlement)
    obs = Observation(
        fsm_state="TEST_SETTLE",
        failure_type=failure_type,
        attempt_count=iteration,
        canonical=canonical,
        raw_problem_desc=problem_desc,
    )

    # Extract features
    if memory.featurizer:
        obs.feature_keys = memory.featurizer.extract_features(obs, MemoryNamespace.TEST)

    # Log event (updates policy weights + item stats + writes to event log)
    memory.log_event(obs, item_ids, reward, iteration=iteration)

    return {
        "execution_log": [
            f"Test memory updated: reward={reward:.2f} for "
            f"{len(item_ids)} items"
        ],
    }
