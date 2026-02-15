#!/usr/bin/env python3
"""
Offline training script for the unified trainable memory system (v2).

This script trains the plan agent's memory policy using a dataset of 
competitive programming problems with known solutions.

Usage:
    # Initialize with seed items only (no training data required)
    python -m scripts.train_plan_policy_v2 --out-dir data/memory

    # Train from dataset
    python -m scripts.train_plan_policy_v2 --data-path data/train/ --out-dir data/memory

    # Customize training parameters
    python -m scripts.train_plan_policy_v2 --data-path data/train/ \\
        --out-dir data/memory --epochs 5 --lr 0.02 --top-k 5

Expected dataset format (JSON files):
    {
        "description": str,              # Problem description
        "tags": ["dp", "graph", ...],    # Algorithm tags
        "time_limit": int,               # Milliseconds
        "space_limit": int,              # MB
        "public_tests": [...],           # Test cases
        "solutions": [                   # Multiple solutions
            {"code": str, "verdict": "AC", "language": "C++"},
            {"code": str, "verdict": "WA", "language": "C++"},
            ...
        ]
    }

Training strategy:
- Problems with AC solutions → positive reward (+1.0)
- Problems with only WA/TLE/RE → negative reward (-0.5)
- Specific failure mode observations → targeted negative updates
"""

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.memory import MemoryClient, MemoryNamespace
from src.memory.types import Observation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("train_plan_policy_v2")


# ======================================================================
# Dataset Loading
# ======================================================================

def load_dataset(data_path: Path) -> List[Dict[str, Any]]:
    """
    Load problem JSONs from directory, file, or jsonl.
    
    Supports:
    - Directory of .json files
    - Single .json file (object or array)
    - Single .jsonl file (one JSON per line)
    """
    problems = []
    
    if not data_path.exists():
        logger.error(f"Data path does not exist: {data_path}")
        return problems
    
    if data_path.is_file():
        if data_path.suffix == ".jsonl":
            # JSONL format
            with open(data_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        try:
                            problems.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipping invalid JSON at line {line_num}: {e}")
        else:
            # Single JSON file
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                problems = data
            else:
                problems = [data]
    
    elif data_path.is_dir():
        # Directory of JSON files
        for json_file in sorted(data_path.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    problems.append(json.load(f))
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping invalid file {json_file.name}: {e}")
        
        # Also check for .jsonl files in directory
        for jsonl_file in sorted(data_path.glob("*.jsonl")):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            problems.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
    
    logger.info(f"Loaded {len(problems)} problems from {data_path}")
    return problems


# ======================================================================
# Feature Extraction
# ======================================================================

def extract_problem_tags(problem: Dict[str, Any]) -> List[str]:
    """Extract and normalize tags from problem data."""
    tags = []
    
    # Direct tags field
    if "tags" in problem:
        tag_data = problem["tags"]
        if isinstance(tag_data, list):
            tags.extend(tag_data)
        elif isinstance(tag_data, str):
            tags.extend([t.strip() for t in tag_data.split(",") if t.strip()])
    
    # Metadata tags
    if "_metadata" in problem and "tags" in problem["_metadata"]:
        meta_tags = problem["_metadata"]["tags"]
        if isinstance(meta_tags, list):
            tags.extend(meta_tags)
        elif isinstance(meta_tags, str):
            tags.extend([t.strip() for t in meta_tags.split(",") if t.strip()])
    
    # Deduplicate and normalize
    normalized = []
    for tag in tags:
        tag = tag.lower().strip().replace(" ", "_")
        if tag and tag not in normalized:
            normalized.append(tag)
    
    return normalized


def classify_verdict(solution: Dict[str, Any]) -> Optional[str]:
    """
    Classify a solution verdict.
    
    Returns:
        "AC" - Accepted
        "WA" - Wrong Answer
        "TLE" - Time Limit Exceeded
        "RE" - Runtime Error
        "CE" - Compilation Error
        None - Unknown/skip
    """
    verdict = solution.get("verdict", "").upper().replace(" ", "_")
    
    if verdict in ("AC", "ACCEPTED", "OK"):
        return "AC"
    elif verdict in ("WA", "WRONG_ANSWER", "WRONGANSWER"):
        return "WA"
    elif verdict in ("TLE", "TIME_LIMIT_EXCEEDED", "TIMELIMITEXCEEDED"):
        return "TLE"
    elif verdict in ("RE", "RUNTIME_ERROR", "RUNTIMEERROR"):
        return "RE"
    elif verdict in ("CE", "COMPILATION_ERROR", "COMPILATIONERROR"):
        return "CE"
    else:
        return None


def build_canonical(problem: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a canonical representation of the problem.
    
    This mimics what the plan_solution_node would produce.
    """
    tags = extract_problem_tags(problem)
    
    canonical = {
        "problem_type": tags[:3] if tags else ["general"],  # Top 3 tags
        "key_elements": tags,
        "objective": problem.get("description", "")[:200],  # First 200 chars
    }
    
    # Add constraints if available
    if "time_limit" in problem:
        canonical["time_limit_ms"] = problem["time_limit"]
    if "space_limit" in problem:
        canonical["space_limit_mb"] = problem["space_limit"]
    
    return canonical


def build_observation(
    problem: Dict[str, Any],
    fsm_state: str = "planning",
    failure_type: Optional[str] = None,
) -> Observation:
    """Build an Observation from problem data."""
    desc = problem.get("description", "")
    canonical = build_canonical(problem)
    
    obs = Observation(
        fsm_state=fsm_state,
        failure_type=failure_type,
        attempt_count=0,
        canonical=canonical,
        raw_problem_desc=desc,
    )
    
    return obs


# ======================================================================
# Training Loop
# ======================================================================

def compute_reward(problem: Dict[str, Any]) -> tuple[float, Dict[str, int]]:
    """
    Compute training reward and failure statistics from solutions.
    
    Returns:
        (reward, failure_stats)
        
    Reward logic:
    - Has AC solution: +1.0
    - Only failed solutions: -0.5
    - No solutions or unknown: 0.0
    """
    solutions = problem.get("solutions", [])
    if not solutions:
        return 0.0, {}
    
    # Classify all solutions
    verdicts = [classify_verdict(s) for s in solutions]
    verdicts = [v for v in verdicts if v is not None]
    
    if not verdicts:
        return 0.0, {}
    
    # Count verdict types
    verdict_counts = {
        "AC": verdicts.count("AC"),
        "WA": verdicts.count("WA"),
        "TLE": verdicts.count("TLE"),
        "RE": verdicts.count("RE"),
        "CE": verdicts.count("CE"),
    }
    
    # Compute reward
    if verdict_counts["AC"] > 0:
        reward = 1.0
    elif any(verdict_counts[k] > 0 for k in ["WA", "TLE", "RE"]):
        reward = -0.5
    else:
        reward = 0.0
    
    return reward, verdict_counts


def train_epoch(
    client: MemoryClient,
    problems: List[Dict[str, Any]],
    top_k: int = 5,
    epoch: int = 1,
) -> Dict[str, float]:
    """
    Train for one epoch over all problems.
    
    Returns:
        Statistics dict with avg_reward, n_updates, etc.
    """
    items = client.store.get_all_items()
    if not items:
        logger.warning("No memory items available for training")
        return {"avg_reward": 0.0, "n_updates": 0}
    
    total_reward = 0.0
    n_updates = 0
    positive_count = 0
    negative_count = 0
    
    for idx, problem in enumerate(problems, 1):
        # Build observation
        obs = build_observation(problem, fsm_state="planning")
        
        # Extract features
        obs.feature_keys = client.featurizer.extract_features(obs, client.namespace)
        
        # Select items via policy
        chosen_items = client.policy.predict(obs, items, top_k=top_k)
        chosen_ids = [item.id for item in chosen_items]
        
        if not chosen_ids:
            continue
        
        # Compute reward
        reward, verdict_counts = compute_reward(problem)
        
        # Update policy
        client.policy.update(obs, chosen_ids, reward)
        
        # Log event
        problem_hash = hashlib.md5(
            problem.get("description", f"problem_{idx}").encode("utf-8")
        ).hexdigest()
        
        client.store.log_event(
            timestamp=None,  # Will use current time
            observation=obs,
            selected_item_ids=chosen_ids,
            reward=reward,
            problem_hash=problem_hash,
            iteration=epoch,
        )
        
        # Update item statistics
        for item_id in chosen_ids:
            client.store.update_item_stats(item_id, reward)
        
        # Track stats
        total_reward += reward
        n_updates += 1
        if reward > 0:
            positive_count += 1
        elif reward < 0:
            negative_count += 1
        
        # Additional targeted updates for specific failure modes
        if verdict_counts.get("TLE", 0) > 0 and verdict_counts.get("AC", 0) == 0:
            # TLE-specific negative update
            fail_obs = build_observation(problem, fsm_state="planning", failure_type="timeout")
            fail_obs.feature_keys = client.featurizer.extract_features(fail_obs, client.namespace)
            client.policy.update(fail_obs, chosen_ids, -0.3)
        
        if verdict_counts.get("WA", 0) > 0 and verdict_counts.get("AC", 0) == 0:
            # WA-specific negative update
            fail_obs = build_observation(problem, fsm_state="planning", failure_type="wrong_answer")
            fail_obs.feature_keys = client.featurizer.extract_features(fail_obs, client.namespace)
            client.policy.update(fail_obs, chosen_ids, -0.2)
        
        # Log progress periodically
        if idx % 10 == 0 or idx == len(problems):
            avg_so_far = total_reward / n_updates if n_updates > 0 else 0.0
            logger.info(
                f"  Progress: {idx}/{len(problems)} problems, "
                f"avg_reward={avg_so_far:.3f}, "
                f"pos={positive_count}, neg={negative_count}"
            )
    
    # Save after epoch
    client.policy.save()
    client.store.save_items()
    
    avg_reward = total_reward / max(n_updates, 1)
    
    return {
        "avg_reward": avg_reward,
        "total_reward": total_reward,
        "n_updates": n_updates,
        "positive_count": positive_count,
        "negative_count": negative_count,
    }


def train(
    client: MemoryClient,
    problems: List[Dict[str, Any]],
    epochs: int = 3,
    top_k: int = 5,
):
    """
    Train the policy over multiple epochs.
    """
    if not problems:
        logger.warning("No training data provided. Skipping training.")
        return
    
    logger.info(f"Starting training: {len(problems)} problems, {epochs} epochs, top_k={top_k}")
    logger.info(f"Memory items: {len(client.store.get_all_items())}")
    
    for epoch in range(1, epochs + 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Epoch {epoch}/{epochs}")
        logger.info(f"{'='*60}")
        
        stats = train_epoch(client, problems, top_k=top_k, epoch=epoch)
        
        logger.info(
            f"\nEpoch {epoch} complete: "
            f"avg_reward={stats['avg_reward']:.3f}, "
            f"updates={stats['n_updates']}, "
            f"positive={stats['positive_count']}, "
            f"negative={stats['negative_count']}"
        )
    
    logger.info("\n" + "="*60)
    logger.info("Training complete!")
    logger.info("="*60)


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Train the plan agent policy using the unified memory system (v2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Path to training data (directory of JSONs, single .json, or .jsonl). "
             "If not provided, only seed items are initialized.",
    )
    
    parser.add_argument(
        "--out-dir",
        type=str,
        default="data/memory",
        help="Output directory for memory database and policy (default: data/memory)",
    )
    
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs (default: 3)",
    )
    
    parser.add_argument(
        "--lr",
        type=float,
        default=0.01,
        help="Learning rate for policy updates (default: 0.01)",
    )
    
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of top items to select per problem (default: 5)",
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Prepare output directory
    out_dir = Path(args.out_dir)
    
    # Initialize memory client
    logger.info(f"Initializing memory client (plan namespace) at {out_dir}")
    
    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": str(out_dir),
            "plan_top_k": args.top_k,
        }
    }
    
    client = MemoryClient(
        namespace=MemoryNamespace.PLAN,
        config=config,
        problem_desc="",  # Not needed for offline training
        canonical={},
    )
    
    if not client.enabled:
        logger.error("Memory client failed to initialize. Check configuration.")
        sys.exit(1)
    
    # Set learning rate
    client.policy.learning_rate = args.lr
    logger.info(f"Learning rate: {args.lr}")
    
    # Display initial state
    items = client.store.get_all_items()
    logger.info(f"Initial memory items: {len(items)}")
    for item in items[:5]:
        logger.info(f"  - {item.text[:60]}... (reward: {item.avg_reward:.3f}, uses: {item.uses})")
    if len(items) > 5:
        logger.info(f"  ... and {len(items) - 5} more")
    
    # Load training data if provided
    if args.data_path:
        data_path = Path(args.data_path)
        problems = load_dataset(data_path)
        
        if problems:
            # Train
            train(client, problems, epochs=args.epochs, top_k=args.top_k)
        else:
            logger.warning("No problems loaded from dataset. Only seed items initialized.")
    else:
        logger.info(
            "No --data-path provided. Memory initialized with seed items only.\n"
            "To train from data, run again with --data-path"
        )
    
    # Display final state
    logger.info(f"\nFinal state:")
    logger.info(f"  Memory directory: {out_dir / 'plan'}")
    logger.info(f"  Database: {out_dir / 'plan' / 'memory.db'}")
    logger.info(f"  Policy: {out_dir / 'plan' / 'policy.json'}")
    
    items = client.store.get_all_items()
    logger.info(f"  Total items: {len(items)}")
    
    # Show top items by reward
    top_items = sorted(items, key=lambda x: x.avg_reward, reverse=True)[:5]
    logger.info(f"\nTop 5 items by average reward:")
    for i, item in enumerate(top_items, 1):
        logger.info(
            f"  {i}. {item.text[:60]}... "
            f"(reward: {item.avg_reward:.3f}, uses: {item.uses})"
        )
    
    logger.info("\n✓ Training complete! Memory system ready for use.")


if __name__ == "__main__":
    main()
