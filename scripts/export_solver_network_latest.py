#!/usr/bin/env python3
"""
Copy skill-graph files from solvita-data ``training_state/latest`` into
``artifacts/solver_network/latest/graph`` and write ``meta.json`` for GraphStore.

Milestone checkpoints under ``training_state/milestones/`` are not copied.

Usage (from repo root)::

    python3 scripts/export_solver_network_latest.py

    python3 scripts/export_solver_network_latest.py \\
        --source /path/to/solvita-data/data/initial_graph/training_state/latest \\
        --dest artifacts/solver_network/latest/graph
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE = REPO_ROOT.parent / "solvita-data" / "data" / "initial_graph" / "training_state" / "latest"
DEFAULT_DEST = REPO_ROOT / "artifacts" / "solver_network" / "latest" / "graph"
MANIFEST_PATH = REPO_ROOT / "artifacts" / "solver_network" / "latest" / "manifest.json"

GRAPH_ID = "solvita-data-initial-graph-training-state-latest"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_minimal_meta(dest: Path) -> None:
    meta = {
        "format_version": "1.0",
        "graph_id": GRAPH_ID,
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _finalize_meta_after_load(dest: Path) -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from skill_graph import GraphStore

    store = GraphStore(str(dest))
    graph = store.load()
    meta = {
        "format_version": "1.0",
        "graph_id": graph.graph_id,
        "stats": graph.stats(),
    }
    (dest / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_manifest(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    artifacts: dict = {}
    for name in ("nodes.jsonl", "edges.jsonl", "meta.json"):
        p = dest / name
        if p.is_file():
            artifacts[name] = {
                "path": str(p.relative_to(REPO_ROOT)),
                "size_bytes": p.stat().st_size,
                "sha256": _sha256_file(p),
            }
    manifest = {
        "module": "solver_network",
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_paths": {
            "latest_dir": str(source.resolve()),
        },
        "artifacts": artifacts,
        "notes": "Copied from solvita-data training_state/latest only; milestones not included.",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Directory with nodes.jsonl and edges.jsonl (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help=f"GraphStore output directory (default: {DEFAULT_DEST})",
    )
    args = parser.parse_args()
    source: Path = args.source.resolve()
    dest: Path = args.dest.resolve()

    for name in ("nodes.jsonl", "edges.jsonl"):
        if not (source / name).is_file():
            print(f"error: missing {source / name}", file=sys.stderr)
            return 1

    dest.mkdir(parents=True, exist_ok=True)
    print(f"Copying {source} -> {dest}")
    for name in ("nodes.jsonl", "edges.jsonl"):
        shutil.copy2(source / name, dest / name)

    _write_minimal_meta(dest)
    print("Loading graph to compute stats and finalize meta.json …")
    _finalize_meta_after_load(dest)
    _write_manifest(source, dest)
    print(f"Wrote {dest / 'meta.json'}")
    print(f"Wrote {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
