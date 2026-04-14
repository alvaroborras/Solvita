"""
Edge hierarchy for the three-layer skill graph.

  QMEdge  Q → M   Problem owns a Method/solution decomposition.
                  Weight: confidence that this M-node is a good decomposition
                  of the Q problem (not trained; set during data construction).

  MSEdge  M → S   A FunctionBlock inside M references a Skill in layer S.
                  Weight: learned probability that this skill is required by
                  the block.  All MSEdges sharing the same (m_node, block_id)
                  origin are normalised so their weights sum to 1.
                  Edges below the pruning threshold are removed after training.

Both edge types carry an arbitrary ``metadata`` dict for extensibility.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .types import EdgeId, EdgeType, NodeId, BlockId, Metadata


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseEdge(ABC):
    """
    Common interface for all edges in the skill graph.

    ``weight`` is the trainable scalar associated with this edge.
    Its semantics differ by subclass (see QMEdge and MSEdge).
    """

    edge_type: EdgeType   # declared by each concrete subclass

    def __init__(
        self,
        source_id: NodeId,
        target_id: NodeId,
        weight:    float                = 1.0,
        edge_id:   Optional[EdgeId]    = None,
        metadata:  Optional[Metadata]  = None,
    ) -> None:
        self.edge_id:   EdgeId   = edge_id or str(uuid.uuid4())
        self.source_id: NodeId   = source_id
        self.target_id: NodeId   = target_id
        self.weight:    float    = weight
        self.metadata:  Metadata = metadata or {}

    # ------------------------------------------------------------------

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialise to a plain Python dict."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> "BaseEdge":
        """Deserialise from a plain Python dict."""

    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"id={self.edge_id!r}, "
            f"{self.source_id!r} → {self.target_id!r}, "
            f"w={self.weight:.4f})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseEdge):
            return NotImplemented
        return self.edge_id == other.edge_id

    def __hash__(self) -> int:
        return hash(self.edge_id)


# ---------------------------------------------------------------------------
# QM-Edge  (Q → M)
# ---------------------------------------------------------------------------

class QMEdge(BaseEdge):
    """
    Connects a problem node (Q) to one of its solution decompositions (M).

    ``weight`` encodes the construction-time confidence that this M-node
    correctly models the Q problem.  It is not updated during RL training
    but can be refined by supervised fine-tuning on held-out labels.

    ``solution_index`` records which correct_solution in QNode this M-node
    was derived from (0-based), enabling traceability.
    """

    edge_type = EdgeType.QM

    def __init__(
        self,
        source_id:      NodeId,
        target_id:      NodeId,
        weight:         float                = 1.0,
        solution_index: int                  = 0,
        trainable:     bool                 = True,
        edge_id:        Optional[EdgeId]    = None,
        metadata:       Optional[Metadata]  = None,
    ) -> None:
        super().__init__(source_id=source_id, target_id=target_id,
                         weight=weight, edge_id=edge_id, metadata=metadata)
        self.solution_index: int = solution_index
        self.trainable:      bool = trainable

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "edge_id":        self.edge_id,
            "edge_type":      self.edge_type.value,
            "source_id":      self.source_id,
            "target_id":      self.target_id,
            "weight":         self.weight,
            "solution_index": self.solution_index,
            "trainable":      self.trainable,
            "metadata":       self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QMEdge":
        return cls(
            edge_id=data["edge_id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            weight=data.get("weight", 1.0),
            solution_index=data.get("solution_index", 0),
            trainable=data.get("trainable", True),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# MS-Edge  (M / FunctionBlock → S)
# ---------------------------------------------------------------------------

class MSEdge(BaseEdge):
    """
    Connects a specific FunctionBlock inside an M-node to a Skill node (S).

    Key invariant (enforced by the graph and trainer):
        For a fixed (m_node_id, block_id), the sum of weights over all
        outgoing MSEdges equals ``MS_GROUP_WEIGHT_SUM`` (default 8.0; was 1.0).

    Lifecycle
    ---------
    1. ``initialised = False``  before weight initialisation.
    2. During ``EdgeWeightInitializer.initialize_all_ms_edges()``, edges with
       non-zero tag overlap get their weight computed and ``initialised = True``.
    3. RL training updates ``weight`` online.
    4. After training, ``SolvitaSkillGraph.prune_ms_edges(threshold)`` removes
       edges with ``weight < threshold``.
    """

    edge_type = EdgeType.MS

    def __init__(
        self,
        source_id:   NodeId,           # ID of the MNode
        target_id:   NodeId,           # ID of the SNode
        block_id:    BlockId,          # Which FunctionBlock within the MNode
        weight:      float             = 0.0,
        initialised: bool              = False,
        trainable:   bool              = True,
        edge_id:     Optional[EdgeId]  = None,
        metadata:    Optional[Metadata] = None,
    ) -> None:
        super().__init__(source_id=source_id, target_id=target_id,
                         weight=weight, edge_id=edge_id, metadata=metadata)
        self.block_id:    BlockId = block_id
        self.initialised: bool    = initialised
        self.trainable:   bool    = trainable

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "edge_id":     self.edge_id,
            "edge_type":   self.edge_type.value,
            "source_id":   self.source_id,
            "target_id":   self.target_id,
            "block_id":    self.block_id,
            "weight":      self.weight,
            "initialised": self.initialised,
            "trainable":   self.trainable,
            "metadata":    self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MSEdge":
        return cls(
            edge_id=data["edge_id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            block_id=data["block_id"],
            weight=data.get("weight", 0.0),
            initialised=data.get("initialised", False),
            trainable=data.get("trainable", True),
            metadata=data.get("metadata", {}),
        )
