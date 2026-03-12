"""
T4.2 Hacker Memory Settlement

Receives the final Hacker Node state (containing sandbox_verdicts, analyst_report,
generator_route_used, hacker_memory_item_ids) and writes a structured learning
signal into the HACK namespace of the trainable Memory system.
"""
from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

from src.memory import MemoryClient, MemoryNamespace, Observation
from src.utils.reward_calculator import compute_hacker_reward

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def settle_hacker_memory(state: "SolvitaState") -> Dict[str, Any]:
    """
    T4.2: Persist the Hacker round's learning signal into HACK memory.

    This node should run after hack_test_node has completed one round
    (whether it broke the target or not). It:
    1. Reads the sandbox_verdicts and compile_failures from state.
    2. Computes the final continuous Reward via compute_hacker_reward().
    3. Replaces the placeholder reward in state with the real value.
    4. Calls memory.log_event() with the Observation including analyst_report
       and generator_route_used for downstream policy learning.
    """
    item_ids = state.get("hacker_memory_item_ids", [])
    if not item_ids:
        logger.debug("[Hack Memory] No item IDs to settle.")
        return {"execution_log": ["Hack memory: no items to settle"]}

    sandbox_verdicts = state.get("sandbox_verdicts", [])
    compile_failures  = state.get("compile_failures", 0)

    # --- Compute real reward (replaces T4.1 placeholder) ---
    reward = compute_hacker_reward(sandbox_verdicts, compile_failures=compile_failures)
    logger.info(f"[Hack Memory] Computed reward = {reward:.3f} "
                f"(verdicts={len(sandbox_verdicts)}, compile_fail={compile_failures})")

    # --- Build Observation with Hacker-specific context ---
    problem_desc = state.get("problem", {}).get("description", "")
    canonical    = state.get("problem", {}).get("canonical", {})
    hack_round   = state.get("hack_round", 0)

    analyst_report      = state.get("analyst_report", {})
    generator_route     = state.get("generator_route_used", "")
    hack_result         = state.get("hack_result", "")
    hack_failure_type   = state.get("hack_failure_type", "")

    memory = MemoryClient(
        namespace=MemoryNamespace.HACK,
        config=state.get("config", {}),
        problem_desc=problem_desc,
        canonical=canonical,
    )

    obs = Observation(
        fsm_state="HACK_SETTLE",
        failure_type=hack_failure_type if hack_result == "BREAK" else None,
        attempt_count=hack_round,
        canonical=canonical,
        raw_problem_desc=problem_desc,
    )

    # Attach Hacker-specific metadata so downstream policy can learn
    # route→outcome correlations and analyst_hypothesis quality.
    obs.extra = {
        "analyst_bug_class": analyst_report.get("bug_class"),
        "analyst_confidence": analyst_report.get("confidence"),
        "generator_route": generator_route,
        "hack_result": hack_result,
    }

    if memory.featurizer:
        obs.feature_keys = memory.featurizer.extract_features(obs, MemoryNamespace.HACK)

    memory.log_event(obs, item_ids, reward, iteration=hack_round)

    return {
        "hacker_reward": reward,   # replace placeholder with real value
        "execution_log": [
            f"Hack memory settled: reward={reward:.3f}, route={generator_route}, "
            f"result={hack_result}, items={len(item_ids)}"
        ],
    }
