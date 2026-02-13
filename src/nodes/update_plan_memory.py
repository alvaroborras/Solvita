"""Update Plan Memory Node - Settle rewards for plan memory after evaluation.

This node runs after unified_check so the outcome (success / failure / pass_rate)
is known. It reads the item IDs that plan_solution_node stored in
state['plan']['memory_item_ids'] and sends a reward signal to the
plan-agent trainable memory system.
"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

from src.memory import MemoryClient, MemoryNamespace, Observation

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _compute_reward(state: Dict[str, Any]) -> float:
    """
    Compute reward for the plan items based on current outcome.

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


def update_plan_memory_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Settle rewards for plan-agent memory items.

    This node is a pass-through for the workflow state — it does not modify
    any business-logic fields. It only updates the persistent plan memory
    (policy weights + item stats + event log) as a side effect.
    """
    item_ids = state.get("plan", {}).get("memory_item_ids", [])

    if not item_ids:
        logger.debug("[Node] update_plan_memory: no item IDs to update")
        return {
            "execution_log": ["Plan memory: no items to update"],
        }

    reward = _compute_reward(state)
    failure_type = _infer_failure_type(state) if reward < 1.0 else None
    iteration = state.get("iteration", 0)

    logger.info(
        f"[Node] Updating plan memory: reward={reward:.2f}, "
        f"items={len(item_ids)}, failure_type={failure_type}"
    )

    problem_desc = state.get("problem", {}).get("description", "")
    canonical = state.get("problem", {}).get("canonical", {})
    
    memory = MemoryClient(
        namespace=MemoryNamespace.PLAN,
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
        obs.feature_keys = memory.featurizer.extract_features(obs, MemoryNamespace.PLAN)
    
    # Log event (updates policy + item stats + writes to event log)
    memory.log_event(obs, item_ids, reward, iteration=iteration)

    return {
        "execution_log": [
            f"Plan memory updated: reward={reward:.2f} for "
            f"{len(item_ids)} items"
        ],
    }
