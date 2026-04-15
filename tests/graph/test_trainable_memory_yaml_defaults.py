"""trainable_memory defaults from config/trainable_memory.yaml and path resolution."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import _merge_runtime_config, create_initial_state


def test_merge_runtime_config_loads_trainable_memory_yaml_and_resolves_data_dir():
    cfg = _merge_runtime_config({})
    tm = cfg["trainable_memory"]
    assert tm["enabled"] is False
    assert tm["plan_top_k"] == 3
    assert tm["solve_top_k"] == 3
    assert tm["oracle_memory_mode"] == "off"
    dd = tm.get("data_dir", "")
    assert dd
    assert Path(dd).is_absolute()
    assert "artifacts/trainable_memory" in dd.replace("\\", "/")


def test_user_trainable_memory_overrides_yaml():
    cfg = _merge_runtime_config(
        {
            "trainable_memory": {
                "enabled": True,
                "solve_top_k": 7,
                "oracle_memory_mode": "runtime_signal",
            }
        }
    )
    tm = cfg["trainable_memory"]
    assert tm["enabled"] is True
    assert tm["solve_top_k"] == 7
    assert tm["oracle_memory_mode"] == "runtime_signal"
    assert tm["plan_top_k"] == 3


def test_empty_trainable_memory_data_dir_override():
    cfg = _merge_runtime_config({"trainable_memory": {"data_dir": ""}})
    assert cfg["trainable_memory"]["data_dir"] == ""


def test_create_initial_state_has_merged_trainable_memory():
    st = create_initial_state(
        {"description": "x", "public_tests": []},
        {},
    )
    tm = st["config"]["trainable_memory"]
    assert tm["enabled"] is False
    assert "data_dir" in tm
