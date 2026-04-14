"""solver_network defaults from config/solver_network.yaml and path resolution."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import _REPO_ROOT, _merge_runtime_config, create_initial_state


def test_merge_runtime_config_loads_yaml_and_resolves_graph_dir():
    cfg = _merge_runtime_config({})
    sn = cfg["solver_network"]
    assert sn["min_llm_skills"] == 1
    assert sn["max_llm_skills"] == 5
    assert sn["skill_candidate_k"] == 20
    gd = sn.get("graph_dir", "")
    assert gd
    assert Path(gd).is_absolute()
    assert (Path(gd).name == "graph" or "solver_network" in gd)


def test_user_solver_network_overrides_yaml():
    cfg = _merge_runtime_config(
        {"solver_network": {"min_llm_skills": 2, "skill_candidate_k": 10}}
    )
    sn = cfg["solver_network"]
    assert sn["min_llm_skills"] == 2
    assert sn["skill_candidate_k"] == 10
    assert sn["max_llm_skills"] == 5


def test_empty_graph_dir_override_disables_path():
    cfg = _merge_runtime_config({"solver_network": {"graph_dir": ""}})
    assert cfg["solver_network"]["graph_dir"] == ""


def test_create_initial_state_has_merged_solver_network():
    st = create_initial_state(
        {"description": "x", "public_tests": []},
        {},
    )
    sn = st["config"]["solver_network"]
    assert sn["min_llm_skills"] == 1
    assert "skill_candidate_k" in sn
