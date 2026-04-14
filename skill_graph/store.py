"""
Persistence layer for the SolvitaSkillGraph.

Format
------
A graph is saved to a directory containing three JSON-Lines files:

    <dir>/nodes.jsonl   – one JSON object per line, each is a serialised node
    <dir>/edges.jsonl   – one JSON object per line, each is a serialised edge
    <dir>/meta.json     – graph-level metadata (id, version, stats, trainer state)

Checkpoint support
------------------
``GraphStore.save_checkpoint(graph, epoch, trainer_state)`` writes to
``<base_dir>/ckpt_<epoch>/`` so multiple training snapshots can coexist.

Usage
-----
    store = GraphStore("/path/to/graph_data")
    store.save(graph)
    graph2 = store.load()
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .edges import MSEdge, QMEdge
from .graph import SolvitaSkillGraph
from .nodes import MNode, QNode, SNode
from .types import EdgeType, NodeType

logger = logging.getLogger(__name__)

_FORMAT_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(path: Path, records):
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# GraphStore
# ---------------------------------------------------------------------------

class GraphStore:
    """
    Handles serialisation and deserialisation of a ``SolvitaSkillGraph``.

    Parameters
    ----------
    base_dir:
        Root directory for persisting graph data.
        Created automatically if it does not exist.
    """

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(
        self,
        graph:         SolvitaSkillGraph,
        trainer_state: Optional[Dict[str, Any]] = None,
        target_dir:    Optional[str]            = None,
    ) -> Path:
        """
        Persist ``graph`` to ``target_dir`` (defaults to ``base_dir``).

        Returns the directory path that was written.
        """
        out = Path(target_dir) if target_dir else self.base_dir
        out.mkdir(parents=True, exist_ok=True)

        # nodes.jsonl
        node_records = [n.to_dict() for n in graph._nodes.values()]
        _write_jsonl(out / "nodes.jsonl", node_records)

        # edges.jsonl
        edge_records = [e.to_dict() for e in graph._edges.values()]
        _write_jsonl(out / "edges.jsonl", edge_records)

        # meta.json
        meta: Dict[str, Any] = {
            "format_version": _FORMAT_VERSION,
            "graph_id":       graph.graph_id,
            "stats":          graph.stats(),
        }
        if trainer_state:
            meta["trainer_state"] = trainer_state
        with (out / "meta.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        logger.info(
            "Graph saved to %s  (%d nodes, %d edges)",
            out, len(node_records), len(edge_records),
        )
        return out

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(
        self,
        source_dir: Optional[str] = None,
    ) -> SolvitaSkillGraph:
        """
        Load a ``SolvitaSkillGraph`` from ``source_dir`` (defaults to
        ``base_dir``).
        """
        src = Path(source_dir) if source_dir else self.base_dir
        meta_path = src / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"No meta.json found in {src}; not a valid graph directory."
            )

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        graph = SolvitaSkillGraph(graph_id=meta.get("graph_id"))

        # Deserialise nodes (Q first, then M, then S – order matters for
        # edge validation although add_node itself is order-independent)
        for rec in _read_jsonl(src / "nodes.jsonl"):
            nt = rec.get("node_type")
            if nt == NodeType.Q.value:
                graph.add_node(QNode.from_dict(rec))
            elif nt == NodeType.M.value:
                graph.add_node(MNode.from_dict(rec))
            elif nt == NodeType.S.value:
                graph.add_node(SNode.from_dict(rec))
            else:
                logger.warning("Unknown node_type %r; skipping.", nt)

        # Deserialise edges
        for rec in _read_jsonl(src / "edges.jsonl"):
            et = rec.get("edge_type")
            try:
                if et == EdgeType.QM.value:
                    graph.add_edge(QMEdge.from_dict(rec))
                elif et == EdgeType.MS.value:
                    graph.add_edge(MSEdge.from_dict(rec))
                else:
                    logger.warning("Unknown edge_type %r; skipping.", et)
            except ValueError as exc:
                logger.warning("Skipping edge %s: %s", rec.get("edge_id"), exc)

        logger.info(
            "Graph loaded from %s  (%s)",
            src, graph,
        )
        return graph

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def save_checkpoint(
        self,
        graph:         SolvitaSkillGraph,
        epoch:         int,
        trainer_state: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Save a versioned snapshot under ``base_dir/ckpt_<epoch>/``."""
        ckpt_dir = self.base_dir / f"ckpt_{epoch:06d}"
        return self.save(graph, trainer_state=trainer_state,
                         target_dir=str(ckpt_dir))

    def load_checkpoint(self, epoch: int) -> SolvitaSkillGraph:
        """Load the snapshot saved at ``epoch``."""
        ckpt_dir = self.base_dir / f"ckpt_{epoch:06d}"
        return self.load(source_dir=str(ckpt_dir))

    def list_checkpoints(self) -> list:
        """Return sorted list of checkpoint epoch numbers found in base_dir."""
        epochs = []
        for d in self.base_dir.iterdir():
            if d.is_dir() and d.name.startswith("ckpt_"):
                try:
                    epochs.append(int(d.name[5:]))
                except ValueError:
                    pass
        return sorted(epochs)

    def latest_checkpoint(self) -> Optional[int]:
        """Return the highest saved checkpoint epoch, or None."""
        ckpts = self.list_checkpoints()
        return ckpts[-1] if ckpts else None
