#!/usr/bin/env python3
"""
Rebuild ``config/tag_whitelist.yaml`` from solver-network ``nodes.jsonl`` Q nodes.

Reads ``tags``, ``tags_level1``, and ``tags_level2`` (normalized snake_case).
Does not load the full graph into memory; streams JSONL.

Usage (repo root)::

    python3 scripts/export_tag_whitelist_from_graph.py
    python3 scripts/export_tag_whitelist_from_graph.py --graph-dir artifacts/solver_network/latest/graph
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = REPO_ROOT / "artifacts" / "solver_network" / "latest" / "graph"
OUT_PATH = REPO_ROOT / "config" / "tag_whitelist.yaml"


def norm(x: str | None) -> str | None:
    if x is None:
        return None
    s = str(x).strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_")
    return s if s else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--graph-dir",
        type=Path,
        default=DEFAULT_GRAPH,
        help=f"Directory containing nodes.jsonl (default: {DEFAULT_GRAPH})",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=OUT_PATH,
        help=f"Output YAML path (default: {OUT_PATH})",
    )
    args = ap.parse_args()
    nodes_path = args.graph_dir / "nodes.jsonl"
    if not nodes_path.is_file():
        raise SystemExit(f"Missing {nodes_path}")

    level1: set[str] = set()
    level2: set[str] = set()
    tags_flat: set[str] = set()

    with nodes_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("node_type") != "Q":
                continue
            for key in ("tags", "tags_level1", "tags_level2"):
                arr = rec.get(key) or []
                if not isinstance(arr, list):
                    continue
                for t in arr:
                    n = norm(str(t))
                    if not n:
                        continue
                    if key == "tags_level1":
                        level1.add(n)
                    elif key == "tags_level2":
                        level2.add(n)
                    else:
                        tags_flat.add(n)

    l1 = sorted(level1 | tags_flat)
    l2 = sorted(level2)

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write("# Allowed algorithmic tags for abstract_problem_node.\n")
        f.write("# Derived from skill-graph QNode.tags, tags_level1, tags_level2 (union, normalized).\n")
        f.write("# Legacy flat `tags` key is still accepted by the loader for backward compatibility.\n\n")
        yaml.safe_dump(
            {"tags_level1": l1, "tags_level2": l2},
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    print(f"Wrote {out} (tags_level1={len(l1)}, tags_level2={len(l2)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
