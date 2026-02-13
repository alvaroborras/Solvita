"""Update Solve Memory Node - Settle rewards for solve memory after evaluation.

This node runs after unified_check so the outcome (success / failure / pass_rate)
is known. It reads the item IDs that generate_code_node stored in
state['solution']['memory_item_ids'] and sends a reward signal to the
solve-agent trainable memory system.
"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

from src.memory import MemoryClient, MemoryNamespace, Observation

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _compute_reward(state: Dict[str, Any]) -> float:
    """
    Compute reward for the solve items based on current outcome.

    Reward scale:
        +1.0  : all tests passed (success)
        -1.0  : reached max_iterations or error
         else : shaping based on pass_rate  (pass_rate - 0.5)
                so 100% -> +0.5, 50% -> 0.0, 0% -> -0.5
    """
    status = state.get("status", "pending")

    if status == "success":
        return 1.0
    elif status in ("max_iterations", "error"):
        return -1.0
    else:
        pass_rate = state.get("tests", {}).get("pass_rate", 0.0)
        return pass_rate - 0.5


def _infer_failure_type(state: Dict[str, Any]) -> str:
    """Infer failure type from state for policy context."""
    if not state.get("solution", {}).get("compilation_success", False):
        return "COMPILE_FAIL"

    pass_rate = state.get("tests", {}).get("pass_rate", 0.0)
    if pass_rate == 0.0:
        # Check if it was a timeout
        test_results = state.get("tests", {}).get("test_results", [])
        if any(r.get("error") == "Timeout" for r in test_results):
            return "TIMEOUT"
        return "SOLVE_WA"

    if pass_rate < 1.0:
        return "SOLVE_WA"

    return ""  # No failure


def update_solve_memory_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Settle rewards for solve-agent memory items.

    This node is a pass-through for the workflow state — it does not modify
    any business-logic fields. It only updates the persistent solve memory
    (policy weights + item stats + event log) as a side effect.
    """
    item_ids = state.get("solution", {}).get("memory_item_ids", [])

    if not item_ids:
        logger.debug("[Node] update_solve_memory: no item IDs to update")
        return {
            "execution_log": ["Solve memory: no items to update"],
        }

    reward = _compute_reward(state)
    failure_type = _infer_failure_type(state) if reward < 1.0 else None
    iteration = state.get("iteration", 0)

    logger.info(
        f"[Node] Updating solve memory: reward={reward:.2f}, "
        f"items={len(item_ids)}, failure_type={failure_type}"
    )

    problem_desc = state.get("problem", {}).get("description", "")
    canonical = state.get("problem", {}).get("canonical", {})
    
    memory = MemoryClient(
        namespace=MemoryNamespace.SOLVE,
        config=state["config"],
        problem_desc=problem_desc,
        canonical=canonical,
    )

    # Create observation for event logging
    obs = Observation(
        fsm_state="SOLVE_CHECK",
        failure_type=failure_type,
        attempt_count=iteration,
        canonical=canonical,
        raw_problem_desc=problem_desc,
    )
    
    # Extract features
    if memory.featurizer:
        obs.feature_keys = memory.featurizer.extract_features(obs, MemoryNamespace.SOLVE)
    
    # Log event (updates policy + item stats + writes to event log)
    memory.log_event(obs, item_ids, reward, iteration=iteration)

    return {
        "execution_log": [
            f"Solve memory updated: reward={reward:.2f} for "
            f"{len(item_ids)} items"
        ],
    }
