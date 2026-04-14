import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.solver_network.adapter import build_solver_network_block


def test_solver_adapter_disabled_returns_empty():
    state = {"problem": {"description": "x", "tags_selected": [], "canonical": {}}, "plan": {}}
    cfg = {"solver_network": {"enabled": False}}
    assert build_solver_network_block(state, cfg) == ""


def test_solver_adapter_missing_graph_dir_returns_empty():
    state = {"problem": {"description": "x", "tags_selected": [], "canonical": {}}, "plan": {}}
    cfg = {"solver_network": {"enabled": True, "graph_dir": ""}}
    assert build_solver_network_block(state, cfg) == ""
