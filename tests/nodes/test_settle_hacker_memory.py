import pytest
from unittest.mock import MagicMock
from src.nodes.settle_hacker_memory import settle_hacker_memory

@pytest.fixture
def base_state():
    return {
        "hacker_memory_item_ids": ["id1", "id2"],
        "sandbox_verdicts": [{"verdict": "VALID_BUT_SAFE"}],
        "compile_failures": 0,
        "problem": {"description": "problem", "canonical": {"id": 1}},
        "config": {"k": 3},
        "hack_round": 1,
        "analyst_report": {"bug_class": "overflow", "confidence": "high"},
        "generator_route_used": "semantic",
        "hack_result": "SAFE",
        "hack_failure_type": "NONE"
    }

def test_settle_hacker_early_return_no_items(monkeypatch):
    """If item_ids is empty, it should early return."""
    # Ensure MemoryClient is not instantiated
    mock_mc = MagicMock()
    monkeypatch.setattr("src.nodes.settle_hacker_memory.MemoryClient", mock_mc)
    
    state = {"hacker_memory_item_ids": []}
    result = settle_hacker_memory(state)
    
    assert "execution_log" in result
    assert "no items to settle" in result["execution_log"][0]
    mock_mc.assert_not_called()

def test_settle_hacker_computes_reward_and_logs_event(base_state, monkeypatch):
    """It should compute reward and call log_event on MemoryClient."""
    mock_mem_instance = MagicMock()
    mock_mem_instance.featurizer = None
    monkeypatch.setattr("src.nodes.settle_hacker_memory.MemoryClient", lambda **kw: mock_mem_instance)
    
    # Mock reward calculator to return a fixed 0.5
    monkeypatch.setattr("src.nodes.settle_hacker_memory.compute_hacker_reward", lambda v, compile_failures: 0.5)

    result = settle_hacker_memory(base_state)
    
    # Assert reward replaced
    assert result["hacker_reward"] == 0.5
    
    # Assert log_event called
    assert mock_mem_instance.log_event.call_count == 1
    call_args = mock_mem_instance.log_event.call_args[0]
    obs = call_args[0]
    
    # Assert extra info populated
    assert obs.extra["analyst_bug_class"] == "overflow"
    assert obs.extra["generator_route"] == "semantic"
    assert obs.extra["hack_result"] == "SAFE"

def test_settle_hacker_extracts_features_if_present(base_state, monkeypatch):
    """If memory client has a featurizer, it should be called."""
    mock_mem_instance = MagicMock()
    mock_featurizer = MagicMock()
    mock_featurizer.extract_features.return_value = ["feat1", "feat2"]
    mock_mem_instance.featurizer = mock_featurizer
    monkeypatch.setattr("src.nodes.settle_hacker_memory.MemoryClient", lambda **kw: mock_mem_instance)
    
    monkeypatch.setattr("src.nodes.settle_hacker_memory.compute_hacker_reward", lambda *a, **kw: 1.0)

    settle_hacker_memory(base_state)
    
    assert mock_featurizer.extract_features.call_count == 1
    call_args = mock_mem_instance.log_event.call_args[0]
    obs = call_args[0]
    assert obs.feature_keys == ["feat1", "feat2"]

def test_settle_hacker_sets_failure_type_only_on_break(base_state, monkeypatch):
    """Failure type should be attached to Observation only if hack_result == BREAK."""
    mock_mem_instance = MagicMock()
    monkeypatch.setattr("src.nodes.settle_hacker_memory.MemoryClient", lambda **kw: mock_mem_instance)
    monkeypatch.setattr("src.nodes.settle_hacker_memory.compute_hacker_reward", lambda *a, **kw: 1.0)

    # 1. Test SAFE -> None
    base_state["hack_result"] = "SAFE"
    base_state["hack_failure_type"] = "NONE"
    settle_hacker_memory(base_state)
    obs1 = mock_mem_instance.log_event.call_args[0][0]
    assert obs1.failure_type is None

    # 2. Test BREAK -> WA
    base_state["hack_result"] = "BREAK"
    base_state["hack_failure_type"] = "WA"
    settle_hacker_memory(base_state)
    obs2 = mock_mem_instance.log_event.call_args[0][0]
    assert obs2.failure_type == "WA"


def test_settle_hacker_penalizes_generation_failure_without_valid_verdicts(monkeypatch):
    mock_mem = MagicMock()
    mock_mem.featurizer = None
    monkeypatch.setattr("src.nodes.settle_hacker_memory.MemoryClient", lambda **kw: mock_mem)

    state = {
        "hacker_memory_item_ids": ["id1"],
        "sandbox_verdicts": [],
        "compile_failures": 0,
        "problem": {"description": "desc", "canonical": {}},
        "config": {"trainable_memory": {"enabled": True, "data_dir": "data/memory"}},
        "hack_round": 1,
        "analyst_report": {},
        "generator_route_used": "failed",
        "hack_result": "GEN_FAILED",
        "hack_failure_type": "NONE",
        "generator_failure_kind": "validator_rejected",
    }

    result = settle_hacker_memory(state)

    assert result["hacker_reward"] < 0.0
