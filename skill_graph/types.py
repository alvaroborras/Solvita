"""
Shared enumerations, type aliases, and lightweight value objects used
throughout the skill-graph framework.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any


# ---------------------------------------------------------------------------
# Node / edge taxonomy
# ---------------------------------------------------------------------------

class NodeType(Enum):
    Q = "Q"   # Problem node (training-set question)
    M = "M"   # Method node  (decomposition + error experience)
    S = "S"   # Skill node   (knowledge-base entry)


class EdgeType(Enum):
    QM = "QM"  # Q → M  (problem owns a method/solution)
    MS = "MS"  # M → S  (function block references a skill)


# ---------------------------------------------------------------------------
# Dataset provenance
# ---------------------------------------------------------------------------

class Dataset(str, Enum):
    """Known dataset identifiers used in the training corpus."""
    CODEFORCES   = "codeforces"
    LEETCODE     = "leetcode"
    ATCODER      = "atcoder"
    CODECHEF     = "codechef"
    UNKNOWN      = "unknown"

    @classmethod
    def from_str(cls, value: str) -> "Dataset":
        try:
            return cls(value.lower())
        except ValueError:
            return cls.UNKNOWN


# ---------------------------------------------------------------------------
# Complexity tier  (used in SNode for quick filtering)
# ---------------------------------------------------------------------------

class ComplexityTier(str, Enum):
    O1        = "O(1)"
    OLOGN     = "O(log n)"
    ON        = "O(n)"
    ONLOGN    = "O(n log n)"
    ON2       = "O(n^2)"
    ON3       = "O(n^3)"
    OEXP      = "O(2^n) or higher"
    UNKNOWN   = "unknown"


# ---------------------------------------------------------------------------
# RL training signals
# ---------------------------------------------------------------------------

class Outcome(Enum):
    """Final verdict of a solver run, used to shape the RL reward."""
    ACCEPTED          = auto()
    WRONG_ANSWER      = auto()
    TIME_LIMIT        = auto()
    MEMORY_LIMIT      = auto()  # MLE / 超空间
    RUNTIME_ERROR     = auto()
    COMPILATION_ERROR = auto()
    PARTIAL           = auto()


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

NodeId  = str
EdgeId  = str
BlockId = str   # ID of a FunctionBlock inside an MNode
TagSet  = List[str]

# Sparse weight table: (source_id, target_id) → float
WeightTable = Dict[Tuple[str, str], float]

# Generic key-value metadata attached to any node or edge
Metadata = Dict[str, Any]
