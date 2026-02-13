"""Unified Trainable Memory.

This module provides a unified architecture for trainable memory across
plan/solve/test agents, with namespace isolation, event logging, and
explicit bipartite edge-weight learning.
"""

from src.memory.types import (
    MemoryNamespace,
    MemoryItem,
    MemoryEvent,
    Observation,
)
from src.memory.client import MemoryClient

__all__ = [
    "MemoryNamespace",
    "MemoryItem",
    "MemoryEvent",
    "Observation",
    "MemoryClient",
]
