"""
SolvitaSkillGraph – the central data structure.

Holds all three node layers and their connecting edges, and exposes
graph-level operations: insertion, adjacency queries, normalisation,
and edge pruning.

Internal adjacency indices are kept in sync automatically on every
``add_node`` / ``add_edge`` call so that hot-path traversals (e.g.,
during inference or RL update steps) avoid linear scans.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

from .edges import BaseEdge, MSEdge, QMEdge
from .nodes import BaseNode, MNode, QNode, SNode
from .types import BlockId, EdgeId, EdgeType, NodeId, NodeType

logger = logging.getLogger(__name__)

# Outgoing MS edges for a fixed (M, block_id) sum to this (was 1.0; scale for ρ path balance).
MS_GROUP_WEIGHT_SUM: float = 8.0

# ---------------------------------------------------------------------------
# Adjacency helpers (private type aliases)
# ---------------------------------------------------------------------------

# Q → [M node IDs]
_QMAdj  = Dict[NodeId, List[NodeId]]
# M, block_id → [S node IDs]
_MSAdj  = Dict[Tuple[NodeId, BlockId], List[NodeId]]
# (source_id, target_id, block_id?) → edge_id  (reverse look-up)
_EdgeIdx = Dict[Tuple, EdgeId]


# ---------------------------------------------------------------------------
# Main graph class
# ---------------------------------------------------------------------------

class SolvitaSkillGraph:
    """
    Three-layer heterogeneous graph:

        Q  ──QMEdge──►  M  ──MSEdge──►  S

    Thread-safety: not thread-safe by design; callers should synchronise
    externally if building the graph in parallel.
    """

    def __init__(self, graph_id: Optional[str] = None) -> None:
        import uuid
        self.graph_id: str = graph_id or str(uuid.uuid4())

        # ── Node registries ────────────────────────────────────────────
        self._nodes:   Dict[NodeId, BaseNode] = {}
        self.q_nodes:  Dict[NodeId, QNode]    = {}
        self.m_nodes:  Dict[NodeId, MNode]    = {}
        self.s_nodes:  Dict[NodeId, SNode]    = {}

        # ── Edge registries ────────────────────────────────────────────
        self._edges:    Dict[EdgeId, BaseEdge]  = {}
        self.qm_edges:  Dict[EdgeId, QMEdge]    = {}
        self.ms_edges:  Dict[EdgeId, MSEdge]    = {}

        # ── Adjacency indices ──────────────────────────────────────────
        # q_id → list of m_ids
        self._qm_adj:   _QMAdj  = defaultdict(list)
        # (m_id, block_id) → list of s_ids
        self._ms_adj:   _MSAdj  = defaultdict(list)
        # (source_id, target_id)         → qm edge_id
        self._qm_index: Dict[Tuple[NodeId, NodeId], EdgeId] = {}
        # (source_id, target_id, block_id) → ms edge_id
        self._ms_index: Dict[Tuple[NodeId, NodeId, BlockId], EdgeId] = {}

    # ==================================================================
    # Node operations
    # ==================================================================

    def add_node(self, node: BaseNode) -> None:
        """Register a node in the appropriate layer registry."""
        if node.node_id in self._nodes:
            logger.debug("Node %s already present; skipping.", node.node_id)
            return
        self._nodes[node.node_id] = node
        if isinstance(node, QNode):
            self.q_nodes[node.node_id] = node
        elif isinstance(node, MNode):
            self.m_nodes[node.node_id] = node
        elif isinstance(node, SNode):
            self.s_nodes[node.node_id] = node
        else:
            raise TypeError(f"Unknown node type: {type(node)}")

    def get_node(self, node_id: NodeId) -> Optional[BaseNode]:
        return self._nodes.get(node_id)

    def remove_node(self, node_id: NodeId) -> None:
        """
        Remove a node and all edges incident to it.
        Use with care – this is O(edges) in the worst case.
        """
        if node_id not in self._nodes:
            return
        node = self._nodes.pop(node_id)
        for registry in (self.q_nodes, self.m_nodes, self.s_nodes):
            registry.pop(node_id, None)

        incident = [
            eid for eid, e in self._edges.items()
            if e.source_id == node_id or e.target_id == node_id
        ]
        for eid in incident:
            self._remove_edge_by_id(eid)

    def iter_nodes(self, node_type: Optional[NodeType] = None) -> Iterator[BaseNode]:
        if node_type is NodeType.Q:
            yield from self.q_nodes.values()
        elif node_type is NodeType.M:
            yield from self.m_nodes.values()
        elif node_type is NodeType.S:
            yield from self.s_nodes.values()
        else:
            yield from self._nodes.values()

    # ==================================================================
    # Edge operations
    # ==================================================================

    def add_edge(self, edge: BaseEdge) -> None:
        """Register an edge and update adjacency indices."""
        if edge.edge_id in self._edges:
            logger.debug("Edge %s already present; skipping.", edge.edge_id)
            return

        # Validate endpoints exist
        if edge.source_id not in self._nodes:
            raise ValueError(
                f"Source node {edge.source_id!r} not found; add it first."
            )
        if edge.target_id not in self._nodes:
            raise ValueError(
                f"Target node {edge.target_id!r} not found; add it first."
            )

        self._edges[edge.edge_id] = edge

        if isinstance(edge, QMEdge):
            self.qm_edges[edge.edge_id] = edge
            self._qm_adj[edge.source_id].append(edge.target_id)
            self._qm_index[(edge.source_id, edge.target_id)] = edge.edge_id

        elif isinstance(edge, MSEdge):
            self.ms_edges[edge.edge_id] = edge
            self._ms_adj[(edge.source_id, edge.block_id)].append(edge.target_id)
            self._ms_index[(edge.source_id, edge.target_id, edge.block_id)] = edge.edge_id

        else:
            raise TypeError(f"Unknown edge type: {type(edge)}")

    def get_edge(self, edge_id: EdgeId) -> Optional[BaseEdge]:
        return self._edges.get(edge_id)

    def get_qm_edge(self, q_id: NodeId, m_id: NodeId) -> Optional[QMEdge]:
        eid = self._qm_index.get((q_id, m_id))
        return self.qm_edges.get(eid) if eid else None

    def get_ms_edge(self, m_id: NodeId, s_id: NodeId,
                    block_id: BlockId) -> Optional[MSEdge]:
        eid = self._ms_index.get((m_id, s_id, block_id))
        return self.ms_edges.get(eid) if eid else None

    def _remove_edge_by_id(self, edge_id: EdgeId) -> None:
        edge = self._edges.pop(edge_id, None)
        if edge is None:
            return
        if isinstance(edge, QMEdge):
            self.qm_edges.pop(edge_id, None)
            adj = self._qm_adj.get(edge.source_id, [])
            if edge.target_id in adj:
                adj.remove(edge.target_id)
            self._qm_index.pop((edge.source_id, edge.target_id), None)
        elif isinstance(edge, MSEdge):
            self.ms_edges.pop(edge_id, None)
            key = (edge.source_id, edge.block_id)
            adj = self._ms_adj.get(key, [])
            if edge.target_id in adj:
                adj.remove(edge.target_id)
            self._ms_index.pop((edge.source_id, edge.target_id, edge.block_id), None)

    # ==================================================================
    # Adjacency queries
    # ==================================================================

    def m_nodes_of(self, q_id: NodeId) -> List[MNode]:
        """Return all M-nodes connected from a Q-node."""
        return [self.m_nodes[mid] for mid in self._qm_adj.get(q_id, [])
                if mid in self.m_nodes]

    def s_nodes_of_block(self, m_id: NodeId,
                         block_id: BlockId) -> List[Tuple[SNode, float]]:
        """
        Return (SNode, weight) pairs for all skills reachable from
        a specific function block in an M-node, sorted by weight descending.
        """
        key    = (m_id, block_id)
        result = []
        for s_id in self._ms_adj.get(key, []):
            snode = self.s_nodes.get(s_id)
            if snode is None:
                continue
            edge = self.get_ms_edge(m_id, s_id, block_id)
            w    = edge.weight if edge else 0.0
            result.append((snode, w))
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def all_ms_edges_of_block(self, m_id: NodeId,
                               block_id: BlockId) -> List[MSEdge]:
        """Return all MSEdge objects leaving a specific (M, block) pair."""
        key = (m_id, block_id)
        out = []
        for s_id in self._ms_adj.get(key, []):
            e = self.get_ms_edge(m_id, s_id, block_id)
            if e:
                out.append(e)
        return out

    # ==================================================================
    # Weight normalisation
    # ==================================================================

    def normalize_ms_weights(self, m_id: NodeId, block_id: BlockId) -> None:
        """
        Renormalise outgoing MS weights for (m_id, block_id) so they sum to
        :data:`MS_GROUP_WEIGHT_SUM`.
        No-op if the total weight is zero (avoids division by zero).
        """
        edges   = self.all_ms_edges_of_block(m_id, block_id)
        total   = sum(e.weight for e in edges)
        if total <= 0.0:
            logger.warning(
                "Block (%s, %s) has zero total MS weight; skipping normalisation.",
                m_id, block_id,
            )
            return
        scale = MS_GROUP_WEIGHT_SUM / total
        for e in edges:
            e.weight *= scale

    def normalize_all_ms_weights(self) -> None:
        """Normalise MS weights for every (M, block) group in the graph."""
        seen: Set[Tuple[NodeId, BlockId]] = set()
        for edge in self.ms_edges.values():
            key = (edge.source_id, edge.block_id)
            if key not in seen:
                seen.add(key)
                self.normalize_ms_weights(edge.source_id, edge.block_id)

    # ==================================================================
    # Edge pruning
    # ==================================================================

    def prune_ms_edges(self, threshold: Optional[float] = None) -> int:
        """
        Remove all MSEdges whose weight is strictly below ``threshold``.

        Default ``threshold`` matches the old ``0.05`` under sum-to-1 semantics
        (i.e. ``0.05 * MS_GROUP_WEIGHT_SUM`` when MS groups sum to 8).

        Returns the number of edges removed.
        After pruning, weights are renormalised for affected (M, block) groups.
        """
        if threshold is None:
            threshold = 0.05 * MS_GROUP_WEIGHT_SUM
        to_remove   = [eid for eid, e in self.ms_edges.items()
                       if e.weight < threshold]
        affected: Set[Tuple[NodeId, BlockId]] = set()
        for eid in to_remove:
            e = self.ms_edges[eid]
            affected.add((e.source_id, e.block_id))
            self._remove_edge_by_id(eid)

        for m_id, block_id in affected:
            self.normalize_ms_weights(m_id, block_id)

        logger.info("Pruned %d MS edges (threshold=%.4f).", len(to_remove), threshold)
        return len(to_remove)

    # ==================================================================
    # Statistics
    # ==================================================================

    def stats(self) -> Dict[str, int]:
        return {
            "q_nodes":   len(self.q_nodes),
            "m_nodes":   len(self.m_nodes),
            "s_nodes":   len(self.s_nodes),
            "qm_edges":  len(self.qm_edges),
            "ms_edges":  len(self.ms_edges),
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
        }

    def __repr__(self) -> str:
        s = self.stats()
        return (
            f"SolvitaSkillGraph(id={self.graph_id!r}, "
            f"Q={s['q_nodes']}, M={s['m_nodes']}, S={s['s_nodes']}, "
            f"QM-edges={s['qm_edges']}, MS-edges={s['ms_edges']})"
        )
