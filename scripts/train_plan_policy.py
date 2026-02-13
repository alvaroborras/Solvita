#!/usr/bin/env python3
"""
Offline pretraining script for the Plan Agent policy network.

This script initialises the plan-agent trainable memory system from a
dataset of competitive-programming problems with standard solutions.

Usage:
    # Seed only (no dataset required)
    python -m scripts.train_plan_policy --out-dir data/memory

    # Train from dataset
    python -m scripts.train_plan_policy --data-path data/train/ --out-dir data/memory

    # Customize training
    python -m scripts.train_plan_policy --data-path data/train/ --out-dir data/memory \\
        --epochs 5 --lr 0.02 --top-k 5

Expected dataset layout (each JSON file = one problem):
    {
        "description": str,
        "tags": ["dp", "graph", ...],
        "time_limit": int,
        "space_limit": int,
        "public_tests": [{"input": str, "output": str}],
        "solutions": [
            {"code": str, "verdict": "AC", "language": "C++"},
            {"code": str, "verdict": "WA", "language": "C++"},
            ...
        ],
        "tests": [{"input": str, "output": str}, ...]
    }

The trainer extracts *positive* signals from AC solutions and *negative*
signals from WA/TLE solutions, then uses them to update the plan policy.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.memory.types import FSMState, FailureType, Observation, Strategy, StrategyType
from src.memory.plan_graph import PlanMemoryGraph
from src.memory.plan_policy import PlanPolicyNetwork

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("train_plan_policy")


# ======================================================================
# Dataset loading
# ======================================================================

def load_dataset(data_path: Path) -> List[Dict[str, Any]]:
    """
    Load problem JSONs from a directory.

    Supports:
    - A directory of .json files
    - A single .jsonl file (one JSON per line)
    - A single .json file containing a list
    """
    problems: List[Dict[str, Any]] = []

    if data_path.is_file():
        if data_path.suffix == ".jsonl":
            with open(data_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        problems.append(json.loads(line))
        else:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                problems = data
            else:
                problems = [data]
    elif data_path.is_dir():
        for p in sorted(data_path.glob("*.json")):
            with open(p, "r", encoding="utf-8") as f:
                problems.append(json.load(f))
        for p in sorted(data_path.glob("*.jsonl")):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        problems.append(json.loads(line))
    else:
        logger.error(f"Data path does not exist: {data_path}")
        sys.exit(1)

    logger.info(f"Loaded {len(problems)} problems from {data_path}")
    return problems


# ======================================================================
# Feature / signal extraction
# ======================================================================

def extract_tags(problem: Dict[str, Any]) -> List[str]:
    """Extract tags from problem metadata."""
    tags = problem.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    # Also check nested _metadata
    meta = problem.get("_metadata", {})
    meta_tags = meta.get("tags", [])
    if isinstance(meta_tags, str):
        meta_tags = [t.strip() for t in meta_tags.split(",") if t.strip()]
    return list(set(tags + meta_tags))


def classify_solution_verdict(solution: Dict[str, Any]) -> Optional[str]:
    """Classify a solution verdict into positive/negative/skip."""
    verdict = solution.get("verdict", "").upper()
    if verdict in ("AC", "ACCEPTED", "OK"):
        return "positive"
    elif verdict in ("WA", "WRONG_ANSWER", "WRONG ANSWER"):
        return "negative_wa"
    elif verdict in ("TLE", "TIME_LIMIT_EXCEEDED", "TIME LIMIT EXCEEDED"):
        return "negative_tle"
    elif verdict in ("RE", "RUNTIME_ERROR", "RUNTIME ERROR"):
        return "negative_re"
    elif verdict in ("CE", "COMPILATION_ERROR", "COMPILATION ERROR"):
        return "negative_ce"
    else:
        return None  # skip unknown


def build_observation(problem: Dict[str, Any], fsm_state: FSMState,
                      failure_type: Optional[FailureType] = None) -> Observation:
    """Build an Observation from problem data."""
    desc = problem.get("description", "")
    tags = extract_tags(problem)
    # Encode tags into the raw_problem_desc field using the convention
    # expected by PlanPolicyNetwork._extract_active_keys
    if tags:
        desc = desc + "||TAGS:" + ",".join(tags)

    return Observation(
        features=[0.0],
        fsm_state=fsm_state,
        failure_type=failure_type,
        raw_problem_desc=desc,
    )


# ======================================================================
# Training loop
# ======================================================================

def train(
    problems: List[Dict[str, Any]],
    graph: PlanMemoryGraph,
    policy: PlanPolicyNetwork,
    epochs: int = 3,
    top_k: int = 5,
):
    """
    Train the plan policy using problem-level reward signals.

    For each problem:
    1. Build an Observation from the problem description + tags.
    2. Run policy.predict() to select top-K strategies.
    3. Compute reward based on whether good solutions exist and
       which failure modes are present in bad solutions.
    4. Update the policy with the reward.

    Over multiple epochs the policy learns which strategies correlate
    with problem tags / difficulty patterns.
    """
    all_strategies = graph.get_all_strategies()
    if not all_strategies:
        logger.warning("No strategies available. Nothing to train.")
        return

    logger.info(
        f"Training plan policy: {len(problems)} problems, "
        f"{len(all_strategies)} strategies, {epochs} epochs, top_k={top_k}"
    )

    for epoch in range(1, epochs + 1):
        total_reward = 0.0
        n_updates = 0

        for problem in problems:
            solutions = problem.get("solutions", [])
            if not solutions:
                continue

            # Classify solutions
            has_ac = any(classify_solution_verdict(s) == "positive" for s in solutions)
            failure_types = set()
            for s in solutions:
                vtype = classify_solution_verdict(s)
                if vtype and vtype.startswith("negative_"):
                    failure_types.add(vtype)

            # Build positive observation (planning for a solvable problem)
            obs = build_observation(problem, FSMState.SOLVE_DRAFT)
            chosen = policy.predict(obs, all_strategies, top_k=top_k)
            chosen_ids = [s.id for s in chosen]

            if not chosen_ids:
                continue

            # Compute reward
            if has_ac:
                reward = 1.0  # Problem has AC solutions => strategies were relevant
            elif failure_types:
                reward = -0.5  # Only bad solutions
            else:
                reward = 0.0  # Unknown

            policy.update(obs, chosen_ids, reward)
            total_reward += reward
            n_updates += 1

            # If there are specific failure types, do a secondary update
            # to teach the policy about failure-recovery context
            if "negative_tle" in failure_types:
                fail_obs = build_observation(
                    problem, FSMState.SOLVE_DRAFT, FailureType.TIMEOUT
                )
                # Strategies that were chosen but led to TLE get negative reward
                policy.update(fail_obs, chosen_ids, -0.3)

            if "negative_wa" in failure_types:
                fail_obs = build_observation(
                    problem, FSMState.SOLVE_DRAFT, FailureType.SOLVE_WA
                )
                policy.update(fail_obs, chosen_ids, -0.2)

        avg_reward = total_reward / max(n_updates, 1)
        logger.info(
            f"Epoch {epoch}/{epochs}: "
            f"{n_updates} updates, avg_reward={avg_reward:.3f}"
        )

    # Save after training
    policy.save()
    graph.save_strategies()
    logger.info("Training complete. Policy and strategies saved.")


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pretrain the plan-agent policy network"
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Path to training data (directory of JSONs, single .json/.jsonl). "
             "If not provided, only seed strategies are initialized.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="data/memory",
        help="Output directory for policy params and strategies",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--lr", type=float, default=0.01, help="Learning rate")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K strategies per problem")

    args = parser.parse_args()
    out_dir = Path(args.out_dir)

    # 1. Initialize graph (loads or seeds strategies)
    graph = PlanMemoryGraph(out_dir)
    graph.initialize()
    logger.info(f"Plan memory graph: {len(graph.strategies)} strategies")

    # 2. Initialize policy
    policy_path = out_dir / "plan_policy_params.json"
    policy = PlanPolicyNetwork(policy_path)
    policy.learning_rate = args.lr
    logger.info(f"Plan policy loaded from {policy_path} (lr={policy.learning_rate})")

    # 3. Train if dataset is provided
    if args.data_path:
        data_path = Path(args.data_path)
        problems = load_dataset(data_path)
        if problems:
            train(problems, graph, policy, epochs=args.epochs, top_k=args.top_k)
        else:
            logger.warning("No problems loaded. Skipping training.")
    else:
        logger.info(
            "No --data-path provided. Only initializing seed strategies. "
            "Run again with --data-path to train from data."
        )
        # Just save the initialized state
        policy.save()
        graph.save_strategies()

    # 4. Summary
    print(f"\nOutput directory: {out_dir}")
    print(f"  Strategies:    {out_dir / 'plan_strategies.jsonl'}")
    print(f"  Policy params: {policy_path}")
    print(f"  Total strategies: {len(graph.strategies)}")
    print(f"  Active strategies: {len(graph.get_all_strategies())}")


if __name__ == "__main__":
    main()
