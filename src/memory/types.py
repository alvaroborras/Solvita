"""Core data types for Trainable Graph Memory."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime


class StrategyType(str, Enum):
    ADVICE = "ADVICE"
    WARNING = "WARNING"


class FSMState(str, Enum):
    # Generator phases
    GEN_DRAFT = "GEN_DRAFT"
    GEN_COMPILE = "GEN_COMPILE" 
    GEN_RUN = "GEN_RUN"
    
    # Validator phases
    VAL_DRAFT = "VAL_DRAFT"
    VAL_COMPILE = "VAL_COMPILE"
    VAL_RUN = "VAL_RUN"
    
    # Checker phases
    CHK_DRAFT = "CHK_DRAFT"
    CHK_COMPILE = "CHK_COMPILE"
    CHK_RUN = "CHK_RUN"
    
    # Solver phases
    SOLVE_DRAFT = "SOLVE_DRAFT"
    SOLVE_COMPILE = "SOLVE_COMPILE"
    SOLVE_RUN = "SOLVE_RUN"
    SOLVE_CHECK = "SOLVE_CHECK"
    
    # Terminal
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class FailureType(str, Enum):
    # Parse/Validation
    JSON_FAIL = "JSON_FAIL"
    
    # Compilation
    COMPILE_FAIL = "COMPILE_FAIL"
    
    # Runtime
    TIMEOUT = "TIMEOUT"
    RUNTIME_ERR = "RUNTIME_ERR"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    
    # Logic
    VAL_REJECT = "VAL_REJECT"      # Generator output rejected by validator
    CHK_FAIL = "CHK_FAIL"          # Checker rejected output
    SOLVE_WA = "SOLVE_WA"          # Solver output mismatch
    
    # Unknown
    UNKNOWN = "UNKNOWN"


@dataclass
class Strategy:
    """A reusable test generation strategy."""
    id: str  # Stable ID (e.g., hash of text)
    text: str  # Human-readable advice
    kind: StrategyType = StrategyType.ADVICE
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Statistics
    uses: int = 0
    avg_reward: float = 0.0
    last_used: str = field(default_factory=lambda: datetime.now().isoformat())
    deprecated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "kind": self.kind,
            "tags": self.tags,
            "created_at": self.created_at,
            "uses": self.uses,
            "avg_reward": self.avg_reward,
            "last_used": self.last_used,
            "deprecated": self.deprecated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Strategy":
        # Handle backward compatibility or missing fields
        return cls(
            id=data["id"],
            text=data["text"],
            kind=StrategyType(data.get("kind", StrategyType.ADVICE)),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            uses=data.get("uses", 0),
            avg_reward=data.get("avg_reward", 0.0),
            last_used=data.get("last_used", datetime.now().isoformat()),
            deprecated=data.get("deprecated", False),
        )


@dataclass
class Observation:
    """Context for retrieving strategies or updating policy."""
    # Problem features
    features: List[float]  # e.g., token hash vector + problem signature bits
    
    # Context
    fsm_state: FSMState
    failure_type: Optional[FailureType] = None
    attempt_count: int = 0
    
    # Raw data (optional, for debugging)
    raw_problem_desc: str = ""
