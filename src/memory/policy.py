"""Policy Network for Trainable Graph Memory.

Manages strategy selection based on problem features and context.
"""

import json
import logging
import random
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np

from src.memory.types import Strategy, Observation

logger = logging.getLogger(__name__)


class PolicyNetwork:
    """
    A lightweight trainable policy for strategy selection.
    
    In v1, this implements a simple linear contextual bandit logic:
    Score(strategy) = base_score + context_weights * features
    
    For simplicity in the initial version without heavy dependencies:
    - We use a dictionary-based weight mapping akin to a sparse linear model.
    - We support basic "online learning" by updating weights based on rewards.
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path
        # Maps feature_hash -> {strategy_id: weight}
        # This is a sparse representation of the policy matrix
        self.weights: Dict[str, Dict[str, float]] = {}
        self.epsilon = 0.1  # Exploration rate
        self.learning_rate = 0.01
        
        if model_path and model_path.exists():
            self.load()

    def load(self):
        try:
            if self.model_path.suffix == '.json':
                with open(self.model_path, 'r') as f:
                    self.weights = json.load(f)
            else:
                # Placeholder for npz loading if we switch to dense numpy arrays later
                pass
            logger.info(f"Loaded policy weights from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load policy weights: {e}")

    def save(self):
        if not self.model_path:
            return
            
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write
            temp_path = self.model_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(self.weights, f, indent=0)
            temp_path.replace(self.model_path)
        except Exception as e:
            logger.error(f"Failed to save policy weights: {e}")

    def predict(self, observation: Observation, available_strategies: List[Strategy], top_k: int = 3) -> List[Strategy]:
        """
        Select best strategies for the given observation.
        """
        if not available_strategies:
            return []

        # 1. Feature extraction (simplified for v1)
        # We assume external featurizer gives us a relevant hash/key
        # For now, we mix global bias with feature-specific bias
        
        # In a real implementation, 'features' would be a dense vector.
        # Here we treat features as sparse keys (e.g., tags)
        active_features = self._extract_active_keys(observation)
        
        scores = []
        for strat in available_strategies:
            score = self._compute_score(strat, active_features)
            # Add small noise for tie-breaking and exploration
            noise = random.uniform(0, 0.01)
            scores.append((score + noise, strat))
            
        # Exploration: with probability epsilon, shuffle a bit? 
        # For code generation, we prefer Exploitation + slight noise, 
        # so standard Top-K on noisy scores is usually sufficient.
        
        scores.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scores[:top_k]]

    def update(self, observation: Observation, strategy_ids: List[str], reward: float):
        """
        Update policy parameters based on reward.
        """
        active_features = self._extract_active_keys(observation)
        
        for sid in strategy_ids:
            for feat in active_features:
                if feat not in self.weights:
                    self.weights[feat] = {}
                
                current_w = self.weights[feat].get(sid, 0.0)
                # Simple gradient update rule: w = w + alpha * reward
                # (Assuming 'reward' is centered, e.g. -0.5 to +1.0)
                new_w = current_w + self.learning_rate * reward
                self.weights[feat][sid] = new_w

    def _extract_active_keys(self, obs: Observation) -> List[str]:
        """Convert observation to sparse string keys."""
        keys = ["GLOBAL_BIAS"]
        
        # Add FSM state bias
        keys.append(f"FSM:{obs.fsm_state.value}")
        
        # Add Failure type bias if present (re-ranking after failure)
        if obs.failure_type:
            keys.append(f"FAIL:{obs.failure_type.value}")
            
        # Add simple tag-based features if available in raw_problem_desc
        # (This is a placeholder; real feature extraction should happen upstream)
        
        return keys

    def _compute_score(self, strategy: Strategy, active_features: List[str]) -> float:
        total = 0.0
        for feat in active_features:
            w_map = self.weights.get(feat, {})
            total += w_map.get(strategy.id, 0.0)
            
        # Boost strategies that match the current context tags
        # e.g., if we are in "FAIL:TIMEOUT", boost "performance" tags
        # This is the "Graph Memory" part blended into the policy
        
        return total
