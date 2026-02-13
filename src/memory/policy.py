"""Bandit-based policy network for memory."""

import json
import logging
import random
import fcntl
from pathlib import Path
from typing import Dict, List, Optional

from src.memory.types import MemoryItem, Observation

logger = logging.getLogger(__name__)


class BanditPolicy:
    """
    Contextual bandit policy for item selection.
    
    score(item) = bias[item] + sum( W[feature, item] for feature in active_features )
    
    Online update:
        W[f, item] <- W[f, item] + alpha * reward
        bias[item] <- bias[item] + alpha * reward
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path
        
        # Sparse weight matrix: feature_key -> {item_id: weight}
        self.weights: Dict[str, Dict[str, float]] = {}
        
        # Per-item bias (global prior)
        self.bias: Dict[str, float] = {}
        
        # Hyperparameters
        self.epsilon = 0.1  # Exploration rate
        self.learning_rate = 0.01
        
        if model_path and model_path.exists():
            self.load()

    def load(self):
        """Load parameters from JSON with file locking."""
        try:
            with open(self.model_path, "r") as f:
                # Acquire shared lock for reading
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            self.weights = data.get("weights", {})
            self.bias = data.get("bias", {})
            self.learning_rate = data.get("learning_rate", self.learning_rate)
            self.epsilon = data.get("epsilon", self.epsilon)
            logger.info(f"Loaded policy from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load policy: {e}")

    def save(self):
        """Persist parameters to JSON (atomic write with file locking)."""
        if not self.model_path:
            return
        
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.model_path.with_suffix(".tmp")
            payload = {
                "weights": self.weights,
                "bias": self.bias,
                "learning_rate": self.learning_rate,
                "epsilon": self.epsilon,
            }
            
            # Write to temp file with exclusive lock
            with open(temp_path, "w") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    json.dump(payload, f, indent=0)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Atomic rename
            temp_path.replace(self.model_path)
            logger.debug(f"Saved policy to {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to save policy: {e}")

    def predict(
        self,
        observation: Observation,
        available_items: List[MemoryItem],
        top_k: int = 3,
    ) -> List[MemoryItem]:
        """
        Select the best items for the given observation.
        
        Returns:
            Top-K items sorted by score (descending).
        """
        if not available_items:
            return []
        
        feature_keys = observation.feature_keys
        
        scores = []
        for item in available_items:
            score = self._compute_score(item, feature_keys)
            # Add noise for tie-breaking and exploration
            noise = random.uniform(0, 0.01)
            scores.append((score + noise, item))
        
        scores.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scores[:top_k]]

    def update(
        self,
        observation: Observation,
        item_ids: List[str],
        reward: float,
    ):
        """
        Update policy weights based on reward.
        
        Reward convention:
            +1.0 = success
            -1.0 = total failure
            0..1 = partial success (e.g., pass_rate)
        """
        feature_keys = observation.feature_keys
        
        for item_id in item_ids:
            # Update bias
            current_bias = self.bias.get(item_id, 0.0)
            self.bias[item_id] = current_bias + self.learning_rate * reward
            
            # Update feature weights
            for feat in feature_keys:
                if feat not in self.weights:
                    self.weights[feat] = {}
                current_w = self.weights[feat].get(item_id, 0.0)
                self.weights[feat][item_id] = current_w + self.learning_rate * reward

    def batch_update(self, records: List[Dict]):
        """
        Offline batch update from training data.
        
        Each record:
        {
            "observation": Observation,
            "item_ids": List[str],
            "reward": float,
        }
        """
        for rec in records:
            self.update(
                observation=rec["observation"],
                item_ids=rec["item_ids"],
                reward=rec["reward"],
            )

    def _compute_score(self, item: MemoryItem, feature_keys: List[str]) -> float:
        """Compute score for a single item."""
        total = self.bias.get(item.id, 0.0)
        
        for feat in feature_keys:
            w_map = self.weights.get(feat, {})
            total += w_map.get(item.id, 0.0)
        
        # Small boost from item tags matching active TAG features
        active_tags = {k.split("TAG:")[-1] for k in feature_keys if k.startswith("TAG:")}
        if active_tags and item.tags:
            overlap = len(active_tags.intersection(set(item.tags)))
            total += 0.05 * overlap  # Small prior boost for tag match
        
        return total
