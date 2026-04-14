"""Smoke import for skill_graph_train (training package; not used by LangGraph workflow)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_graph_train.bootstrap import ensure_import_paths


def test_bootstrap_adds_paths_and_skill_graph_train_imports():
    ensure_import_paths()
    from skill_graph_train.pipeline import (  # noqa: WPS433
        build_planner_input,
        normalize_user_tests,
        run_episode,
    )

    assert callable(run_episode)
    assert callable(build_planner_input)
    assert callable(normalize_user_tests)
