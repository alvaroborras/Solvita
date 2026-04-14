"""
Configure ``sys.path`` so training scripts can import ``skill_graph`` and ``src.*`` from the Solvita repo.

Training entry points: ``skill_graph_train.pipeline.run_episode`` and any ``scripts/train*.py`` you add.
This package does **not** hook into the LangGraph ``run_workflow`` solver path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    # src/skill_graph_train/bootstrap.py -> repo root = parents[2]
    return Path(__file__).resolve().parents[2]


def ensure_import_paths() -> Path:
    """
    Insert the repository root and ``src/`` on ``sys.path`` so ``import skill_graph``,
    ``import skill_graph_train``, and ``import src....`` work.

    Sets ``SOLVITA_CONFIG_PATH`` to ``<repo>/config`` when unset.
    """
    root = _repo_root()
    src = root / "src"
    for p in (root, src):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)

    cfg = root / "config"
    if cfg.is_dir():
        os.environ.setdefault("SOLVITA_CONFIG_PATH", str(cfg))

    sg = root / "skill_graph" / "__init__.py"
    if not sg.is_file():
        raise RuntimeError(
            f"Expected skill_graph package at {root / 'skill_graph'}. "
            "Run from a checkout where skill_graph/ lives next to src/."
        )

    return root


ensure_solvita_paths = ensure_import_paths
