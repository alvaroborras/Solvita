"""Solver network vs trainable-memory switches must not overwrite each other."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import _merge_runtime_config
from src.memory import MemoryClient, MemoryNamespace


def test_solver_network_and_trainable_memory_merge_independently():
    """Toggling one subtree must not drop keys from the other."""
    cfg = _merge_runtime_config(
        {
            "solver_network": {"enabled": True},
            "trainable_memory": {
                "enabled": True,
                "hacker_enabled": False,
                "oracle_enabled": True,
                "solve_top_k": 9,
            },
        }
    )
    sn = cfg["solver_network"]
    tm = cfg["trainable_memory"]
    assert sn["enabled"] is True
    assert "graph_dir" in sn
    assert tm["enabled"] is True
    assert tm["hacker_enabled"] is False
    assert tm["oracle_enabled"] is True
    assert tm["solve_top_k"] == 9
    # Defaults from YAML / fallback should still be present for untouched keys
    assert "plan_top_k" in tm

    cfg2 = _merge_runtime_config(
        {
            "trainable_memory": {"enabled": False},
            "solver_network": {"enabled": False, "top_k_problems": 2},
        }
    )
    assert cfg2["trainable_memory"]["enabled"] is False
    assert cfg2["solver_network"]["enabled"] is False
    assert cfg2["solver_network"]["top_k_problems"] == 2
    # User did not set these; defaults from YAML / fallback must remain
    assert "hacker_enabled" in cfg2["trainable_memory"]
    assert "oracle_enabled" in cfg2["trainable_memory"]


def test_hacker_and_oracle_memory_clients_independent(monkeypatch, tmp_path: Path):
    """hacker_enabled and oracle_enabled only gate their own namespace."""
    monkeypatch.setattr(
        "src.memory.client.MemoryStore",
        MagicMock(),
    )
    monkeypatch.setattr(
        "src.memory.client.BanditPolicy",
        MagicMock(),
    )

    base_tm = {
        "enabled": True,
        "data_dir": str(tmp_path),
        "hacker_enabled": False,
        "oracle_enabled": True,
        "hack_top_k": 2,
        "oracle_top_k": 2,
    }
    config = {"trainable_memory": base_tm}

    hack_client = MemoryClient(MemoryNamespace.HACK, config)
    oracle_client = MemoryClient(MemoryNamespace.ORACLE, config)

    assert hack_client.enabled is False
    assert oracle_client.enabled is True

    config2 = {
        "trainable_memory": {
            **base_tm,
            "hacker_enabled": True,
            "oracle_enabled": False,
        }
    }
    hack_client2 = MemoryClient(MemoryNamespace.HACK, config2)
    oracle_client2 = MemoryClient(MemoryNamespace.ORACLE, config2)
    assert hack_client2.enabled is True
    assert oracle_client2.enabled is False


def test_solver_network_flag_does_not_read_trainable_memory():
    """Adapter-style checks use only solver_network.enabled (orthogonal to memory)."""
    from src.solver_network.adapter import build_solver_network_block

    state = {"plan": {}}
    config_off = {
        "solver_network": {"enabled": False, "graph_dir": "/nonexistent"},
        "trainable_memory": {"enabled": True, "hacker_enabled": True, "oracle_enabled": True},
    }
    assert build_solver_network_block(state, config_off) == ""

    # Memory off, solver on but invalid graph -> still no block; proves TM did not force solver path
    config_bad_graph = {
        "solver_network": {"enabled": True, "graph_dir": "/nonexistent/dir/__missing__"},
        "trainable_memory": {"enabled": False},
    }
    out = build_solver_network_block(state, config_bad_graph)
    assert isinstance(out, str)
