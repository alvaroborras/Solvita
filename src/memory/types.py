"""Core data types for Trainable Memory v2."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime


class MemoryNamespace(str, Enum):
    """Agent-specific memory namespaces."""
    PLAN = "plan"
    SOLVE = "solve"
    TEST = "test"
    HACK = "hack"


@dataclass
class MemoryItem:
    """
    A memory item that can be selected and injected.
    
    The `payload` field is namespace-specific:
    - plan: {problem_tags, subfunctions, canonical_hints}
    - solve: {step_strategies, skills, anti_patterns}
    - test: {constraints_patterns, generation_strategies, validator_pitfalls}
    - hack: {adversarial_patterns, edge_cases}
    """
    id: str  # Stable ID (hash-based or UUID)
    namespace: MemoryNamespace
    text: str  # Human-readable summary
    payload: Dict[str, Any]  # Namespace-specific structured data
    tags: List[str] = field(default_factory=list)
    
    # Statistics
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    uses: int = 0
    avg_reward: float = 0.0
    last_used: str = field(default_factory=lambda: datetime.now().isoformat())
    deprecated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "namespace": self.namespace.value if isinstance(self.namespace, MemoryNamespace) else self.namespace,
            "text": self.text,
            "payload": self.payload,
            "tags": self.tags,
            "created_at": self.created_at,
            "uses": self.uses,
            "avg_reward": self.avg_reward,
            "last_used": self.last_used,
            "deprecated": self.deprecated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        return cls(
            id=data["id"],
            namespace=MemoryNamespace(data["namespace"]),
            text=data["text"],
            payload=data.get("payload", {}),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            uses=data.get("uses", 0),
            avg_reward=data.get("avg_reward", 0.0),
            last_used=data.get("last_used", datetime.now().isoformat()),
            deprecated=data.get("deprecated", False),
        )


@dataclass
class Observation:
    """
    Rich observation for policy network.
    
    Features are extracted from problem.canonical + FSM state + failure type.
    """
    # Context (reused from v1)
    fsm_state: str  # e.g. "SOLVE_DRAFT", "GEN_DRAFT"
    failure_type: Optional[str] = None
    attempt_count: int = 0
    
    # Rich features from canonical problem
    canonical: Dict[str, Any] = field(default_factory=dict)
    
    # Derived feature keys (populated by featurizer)
    feature_keys: List[str] = field(default_factory=list)
    
    # Raw data for debugging
    raw_problem_desc: str = ""


@dataclass
class MemoryEvent:
    """
    A logged event: observation + selected items + outcome reward.
    
    These are append-only and enable trajectory-level analysis.
    """
    timestamp: str
    namespace: MemoryNamespace
    observation: Observation
    selected_item_ids: List[str]
    reward: float
    
    # Optional metadata
    problem_hash: Optional[str] = None
    iteration: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "namespace": self.namespace.value if isinstance(self.namespace, MemoryNamespace) else self.namespace,
            "observation": {
                "fsm_state": self.observation.fsm_state,
                "failure_type": self.observation.failure_type,
                "attempt_count": self.observation.attempt_count,
                "canonical": self.observation.canonical,
                "feature_keys": self.observation.feature_keys,
                "raw_problem_desc": self.observation.raw_problem_desc,
            },
            "selected_item_ids": self.selected_item_ids,
            "reward": self.reward,
            "problem_hash": self.problem_hash,
            "iteration": self.iteration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEvent":
        obs_data = data["observation"]
        obs = Observation(
            fsm_state=obs_data["fsm_state"],
            failure_type=obs_data.get("failure_type"),
            attempt_count=obs_data.get("attempt_count", 0),
            canonical=obs_data.get("canonical", {}),
            feature_keys=obs_data.get("feature_keys", []),
            raw_problem_desc=obs_data.get("raw_problem_desc", ""),
        )
        return cls(
            timestamp=data["timestamp"],
            namespace=MemoryNamespace(data["namespace"]),
            observation=obs,
            selected_item_ids=data["selected_item_ids"],
            reward=data["reward"],
            problem_hash=data.get("problem_hash"),
            iteration=data.get("iteration", 0),
        )
