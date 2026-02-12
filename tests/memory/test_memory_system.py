"""Unit tests for Trainable Graph Memory."""

import json
import shutil
import pytest
from pathlib import Path
from src.memory.types import Strategy, StrategyType, FSMState, FailureType, Observation
from src.memory.graph import MemoryGraph
from src.memory.policy import PolicyNetwork
from src.memory.client import MemoryClient


@pytest.fixture
def temp_memory_dir(tmp_path):
    d = tmp_path / "memory_test"
    d.mkdir()
    return d


def test_strategy_serialization():
    s = Strategy(id="123", text="Use testlib", tags=["test"], kind=StrategyType.WARNING)
    d = s.to_dict()
    assert d["id"] == "123"
    assert d["kind"] == "WARNING"
    
    s2 = Strategy.from_dict(d)
    assert s2.id == s.id
    assert s2.text == s.text


def test_graph_seeding(temp_memory_dir):
    graph = MemoryGraph(temp_memory_dir)
    graph.initialize()
    
    # checks files created
    assert (temp_memory_dir / "strategies.jsonl").exists()
    
    # checks seeding happened
    strats = graph.get_all_strategies()
    assert len(strats) > 0
    assert any("testlib" in s.text for s in strats)


def test_graph_update(temp_memory_dir):
    graph = MemoryGraph(temp_memory_dir)
    graph.initialize()
    
    strats = graph.get_all_strategies()
    sid = strats[0].id
    
    graph.update_strategy_stats(sid, 1.0)
    graph.save_strategies()
    
    # Reload and check
    graph2 = MemoryGraph(temp_memory_dir)
    graph2.initialize()
    s_new = graph2.get_strategy(sid)
    assert s_new.uses == 1
    assert s_new.avg_reward == 1.0


def test_policy_prediction(temp_memory_dir):
    policy = PolicyNetwork(temp_memory_dir / "policy.json")
    
    obs = Observation(
        features=[], 
        fsm_state=FSMState.GEN_DRAFT,
        raw_problem_desc="graph problem"
    )
    
    strats = [
        Strategy(id="s1", text="advice1"),
        Strategy(id="s2", text="advice2")
    ]
    
    # Predict
    chosen = policy.predict(obs, strats, top_k=1)
    assert len(chosen) == 1
    
    # Update
    policy.update(obs, ["s1"], -0.5)
    policy.save()
    
    assert (temp_memory_dir / "policy.json").exists()


def test_client_integration(temp_memory_dir):
    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": str(temp_memory_dir),
            "top_k": 2
        }
    }
    
    client = MemoryClient(config, "test problem")
    assert client.enabled
    
    # 1. Get advice (should return seeded advice)
    advice = client.get_advice(FSMState.GEN_DRAFT)
    assert "[Strategies from Memory]" in advice
    assert len(client.last_suggested_ids) > 0
    
    # 2. Log outcome
    client.log_outcome(FSMState.GEN_DRAFT, FailureType.COMPILE_FAIL, -1.0)
    
    # 3. Check persistence
    assert (temp_memory_dir / "strategies.jsonl").exists()
    assert (temp_memory_dir / "policy_params.json").exists()


def test_client_disabled(temp_memory_dir):
    config = {"trainable_memory": {"enabled": False}}
    client = MemoryClient(config, "test problem")
    assert not client.enabled
    assert client.get_advice("GEN_DRAFT") == ""
    # Should not crash
    client.log_outcome("GEN_DRAFT", "FAIL", -1.0) 
