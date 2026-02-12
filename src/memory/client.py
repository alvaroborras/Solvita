"""Trainable Memory Client.

The main entry point for interacting with the memory system.
"""

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from src.memory.types import Strategy, StrategyType, FSMState, FailureType, Observation
from src.memory.graph import MemoryGraph
from src.memory.policy import PolicyNetwork

logger = logging.getLogger(__name__)


class MemoryClient:
    """
    Client for the Trainable Graph Memory system.
    
    Usage:
        client = MemoryClient(config)
        advice = client.get_advice(problem_desc, fsm_state)
        client.log_outcome(fsm_state, failure_type, reward)
    """

    def __init__(self, config: Dict[str, Any], problem_desc: str = ""):
        self.config = config or {}
        self.enabled = self.config.get("trainable_memory", {}).get("enabled", False)
        self.top_k = self.config.get("trainable_memory", {}).get("top_k", 3)
        self.data_dir = Path(self.config.get("trainable_memory", {}).get("data_dir", "data/memory"))
        
        self.problem_desc = problem_desc
        # Compute stable problem hash (v1: simple md5 of description)
        self.problem_hash = hashlib.md5(problem_desc.encode("utf-8")).hexdigest()
        
        self.graph: Optional[MemoryGraph] = None
        self.policy: Optional[PolicyNetwork] = None
        
        # Last suggested strategy IDs (for update tracking)
        self.last_suggested_ids: List[str] = []

        if self.enabled:
            logger.info(f"Initializing Trainable Memory at {self.data_dir}")
            try:
                self.graph = MemoryGraph(self.data_dir)
                self.graph.initialize()
                
                self.policy = PolicyNetwork(self.data_dir / "policy_params.json")
            except Exception as e:
                logger.error(f"Failed to initialize memory, disabling for this run: {e}")
                self.enabled = False
        else:
            logger.debug("Trainable Memory is disabled in config.")

    def get_advice(self, fsm_state: Union[str, FSMState], failure_type: Optional[str] = None, attempt: int = 0) -> str:
        """
        Retrieve formatted advice string for the current context.
        """
        if not self.enabled or not self.graph or not self.policy:
            return ""

        try:
            # Convert strings to Enums
            if isinstance(fsm_state, str):
                try:
                    fsm_state = FSMState(fsm_state)
                except ValueError:
                    fsm_state = FSMState.GEN_DRAFT
            
            f_type = None
            if failure_type:
                try:
                    f_type = FailureType(failure_type)
                except ValueError:
                    f_type = FailureType.UNKNOWN

            # Prepare observation
            obs = Observation(
                features=[0.0],  # TODO: real features
                fsm_state=fsm_state,
                failure_type=f_type,
                attempt_count=attempt,
                raw_problem_desc=self.problem_desc
            )

            # Get candidates
            candidates = self.graph.get_all_strategies()
            
            # Predict
            chosen = self.policy.predict(obs, candidates, top_k=self.top_k)
            self.last_suggested_ids = [s.id for s in chosen]
            
            if not chosen:
                return ""

            # Format output
            lines = ["\n[Strategies from Memory]"]
            for s in chosen:
                prefix = "ADVICE" if s.kind == StrategyType.ADVICE else "WARNING"
                lines.append(f"- {prefix}: {s.text}")
            
            return "\n".join(lines) + "\n"

        except Exception as e:
            logger.error(f"Error retrieving advice: {e}")
            return ""

    def log_outcome(self, 
                    fsm_state: Union[str, FSMState], 
                    failure_type: Optional[str], 
                    reward: float):
        """
        Update memory with the outcome of the last action.
        """
        if not self.enabled or not self.last_suggested_ids:
            return

        try:
            # Normalize inputs
            if isinstance(fsm_state, str):
                try:
                    state_enum = FSMState(fsm_state)
                except ValueError:
                    state_enum = FSMState.GEN_DRAFT
            else:
                state_enum = fsm_state

            f_type = None
            if failure_type:
                try:
                    f_type = FailureType(failure_type)
                except ValueError:
                    f_type = FailureType.UNKNOWN

            obs = Observation(
                features=[0.0],
                fsm_state=state_enum,
                failure_type=f_type,
                raw_problem_desc=self.problem_desc
            )

            # Update Policy
            self.policy.update(obs, self.last_suggested_ids, reward)
            self.policy.save()

            # Update Graph Stats
            for sid in self.last_suggested_ids:
                self.graph.update_strategy_stats(sid, reward)
            self.graph.save_strategies()
            
            logger.info(f"Memory updated: reward={reward:.2f} for {len(self.last_suggested_ids)} strategies")
            
        except Exception as e:
            logger.error(f"Error updating memory: {e}")
