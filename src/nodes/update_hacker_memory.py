"""Update Hacker Memory Node - Settle rewards for adversarial test generation.

This node runs after the hack success/failure outcome is evaluated in 
train_hacker_input.py. It reads the item IDs that hack_test_node stored in
state['hacker_memory_item_ids'] and sends a final reward signal to the
hacker-agent trainable memory system.

The reward is dynamically calculated during the training loop.
"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

from src.memory import MemoryClient, MemoryNamespace, Observation

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def update_hacker_memory_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Settle rewards for hacker-agent memory items.
    
    Item IDs come from state['hacker_memory_item_ids'], populated by
    hack_test_node at the time of memory injection.
    Reward is passed explicitly via state['hacker_reward'].
    """
    item_ids = state.get("hacker_memory_item_ids", [])

    if not item_ids:
        logger.debug("[Node] update_hacker_memory: no item IDs to update")
        return {
            "execution_log": ["Hacker memory: no items to update"],
        }

    # Extract dynamic reward calculated in train script
    reward = state.get("hacker_reward", 0.0)
    
    # Simple failure inference logic based on whether we cracked it
    failure_type = "HACK_FAILED" if reward < 0 else None
    iteration = state.get("iteration", 0)

    logger.info(
        f"[Node] Updating hacker memory: reward={reward:.2f}, "
        f"items={len(item_ids)}, failure_type={failure_type}"
    )

    problem_desc = state.get("problem", {}).get("description", "")
    canonical = state.get("problem", {}).get("canonical", {})

    memory = MemoryClient(
        namespace=MemoryNamespace.HACK,
        config=state["config"],
        problem_desc=problem_desc,
        canonical=canonical,
    )

    # Create observation for event logging (post-generation settlement)
    obs = Observation(
        fsm_state="HACK_SETTLE",
        failure_type=failure_type,
        attempt_count=iteration,
        canonical=canonical,
        raw_problem_desc=problem_desc,
    )

    # Extract features
    if memory.featurizer:
        obs.feature_keys = memory.featurizer.extract_features(obs, MemoryNamespace.HACK)

    # Log event (updates policy weights + item stats + writes to event log)
    memory.log_event(obs, item_ids, reward, iteration=iteration)

    return {
        "execution_log": [
            f"Hacker memory updated: reward={reward:.2f} for "
            f"{len(item_ids)} items"
        ],
    }
