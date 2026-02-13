"""Unit tests for Trainable Memory."""

import json
import pytest
from pathlib import Path

from src.memory.types import (
    MemoryNamespace,
    MemoryItem,
    MemoryEvent,
    Observation,
)
from src.memory.store import MemoryStore
from src.memory.policy import BanditPolicy
from src.memory.featurizer import Featurizer
from src.memory.client import MemoryClient


@pytest.fixture
def temp_memory_dir(tmp_path):
    d = tmp_path / "memory_test"
    d.mkdir()
    return d


def test_memory_item_serialization():
    """Test MemoryItem to_dict / from_dict."""
    item = MemoryItem(
        id="test123",
        namespace=MemoryNamespace.PLAN,
        text="Test strategy",
        payload={"problem_tags": ["dp"], "subfunctions": ["build_dp"]},
        tags=["test"],
    )
    d = item.to_dict()
    assert d["id"] == "test123"
    assert d["namespace"] == "plan"
    
    item2 = MemoryItem.from_dict(d)
    assert item2.id == item.id
    assert item2.namespace == item.namespace


def test_store_seeding(temp_memory_dir):
    """Test that store seeds items on cold start."""
    store = MemoryStore(MemoryNamespace.PLAN, temp_memory_dir)
    store.initialize()
    
    # Check files created
    assert (temp_memory_dir / "plan" / "items.jsonl").exists()
    
    # Check seeding happened
    items = store.get_all_items()
    assert len(items) > 0
    assert any("dp" in item.text.lower() or "dynamic" in item.text.lower() for item in items)


def test_store_persistence(temp_memory_dir):
    """Test that items persist across store instances."""
    store1 = MemoryStore(MemoryNamespace.SOLVE, temp_memory_dir)
    store1.initialize()
    
    items_before = store1.get_all_items()
    assert len(items_before) > 0
    
    # Update an item
    item_id = items_before[0].id
    store1.update_item_stats(item_id, 1.0)
    store1.save_items()
    
    # Reload
    store2 = MemoryStore(MemoryNamespace.SOLVE, temp_memory_dir)
    store2.initialize()
    item_after = store2.get_item(item_id)
    
    assert item_after.uses == 1
    assert item_after.avg_reward == 1.0


def test_event_logging(temp_memory_dir):
    """Test event logging to events.jsonl."""
    store = MemoryStore(MemoryNamespace.TEST, temp_memory_dir)
    store.initialize()
    
    obs = Observation(
        fsm_state="GEN_DRAFT",
        failure_type=None,
        attempt_count=0,
        canonical={"problem_type": ["array"]},
        feature_keys=["FSM:GEN_DRAFT", "TYPE:array"],
    )
    
    event = MemoryEvent(
        timestamp="2026-02-13T12:00:00",
        namespace=MemoryNamespace.TEST,
        observation=obs,
        selected_item_ids=["item1", "item2"],
        reward=0.5,
    )
    
    store.log_event(event)
    
    # Check event file exists
    events_path = temp_memory_dir / "test" / "events.jsonl"
    assert events_path.exists()
    
    # Read back
    events = store.get_events()
    assert len(events) == 1
    assert events[0].reward == 0.5


def test_policy_prediction(temp_memory_dir):
    """Test policy network prediction."""
    policy = BanditPolicy(temp_memory_dir / "test_policy.json")
    
    obs = Observation(
        fsm_state="SOLVE_DRAFT",
        feature_keys=["FSM:SOLVE_DRAFT", "TAG:dp"],
    )
    
    items = [
        MemoryItem(id="s1", namespace=MemoryNamespace.SOLVE, text="advice1", payload={}),
        MemoryItem(id="s2", namespace=MemoryNamespace.SOLVE, text="advice2", payload={}),
    ]
    
    # Predict
    chosen = policy.predict(obs, items, top_k=1)
    assert len(chosen) == 1
    
    # Update
    policy.update(obs, ["s1"], -0.5)
    policy.save()
    
    assert (temp_memory_dir / "test_policy.json").exists()


def test_featurizer_extraction():
    """Test feature extraction from canonical problem."""
    featurizer = Featurizer()
    
    obs = Observation(
        fsm_state="SOLVE_DRAFT",
        failure_type="TIMEOUT",
        attempt_count=2,
        canonical={
            "problem_type": ["dp", "optimization"],
            "constraints": {"n": "1e5"},
            "key_elements": ["prefix_sum", "sliding_window"],
        },
    )
    
    features = featurizer.extract_features(obs, MemoryNamespace.PLAN)
    
    assert "GLOBAL_BIAS" in features
    assert "FSM:SOLVE_DRAFT" in features
    assert "FAIL:TIMEOUT" in features
    assert "ATTEMPT:2" in features
    assert "TYPE:dp" in features
    assert "ELEM:prefix_sum" in features


def test_client_integration(temp_memory_dir):
    """Test full client workflow."""
    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": str(temp_memory_dir),
            "plan_top_k": 2,
        }
    }
    
    client = MemoryClient(
        namespace=MemoryNamespace.PLAN,
        config=config,
        problem_desc="test problem",
        canonical={"problem_type": ["dp"]},
    )
    
    assert client.enabled
    
    # Get injection
    injection_text, item_ids = client.get_injection(
        fsm_state="SOLVE_DRAFT",
        failure_type=None,
        attempt_count=0,
    )
    
    assert len(item_ids) > 0
    assert "Memory: PLAN strategies" in injection_text or injection_text == ""
    
    # Log event
    obs = Observation(
        fsm_state="SOLVE_DRAFT",
        canonical={"problem_type": ["dp"]},
    )
    client.log_event(obs, item_ids, 1.0, iteration=0)
    
    # Check persistence
    assert (temp_memory_dir / "plan" / "items.jsonl").exists()
    assert (temp_memory_dir / "plan" / "policy.json").exists()
    assert (temp_memory_dir / "plan" / "events.jsonl").exists()


def test_namespace_isolation(temp_memory_dir):
    """Test that different namespaces have isolated storage."""
    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": str(temp_memory_dir),
        }
    }
    
    plan_client = MemoryClient(
        namespace=MemoryNamespace.PLAN,
        config=config,
        problem_desc="test",
    )
    
    solve_client = MemoryClient(
        namespace=MemoryNamespace.SOLVE,
        config=config,
        problem_desc="test",
    )
    
    # Check separate directories
    assert (temp_memory_dir / "plan").exists()
    assert (temp_memory_dir / "solve").exists()
    
    # Check separate items
    plan_items = plan_client.store.get_all_items()
    solve_items = solve_client.store.get_all_items()
    
    # Items should be different (different seed sets)
    plan_texts = {item.text for item in plan_items}
    solve_texts = {item.text for item in solve_items}
    
    # At least some items should be unique to each namespace
    assert len(plan_texts.intersection(solve_texts)) < len(plan_texts)


def test_client_disabled(temp_memory_dir):
    """Test that client gracefully handles disabled state."""
    config = {"trainable_memory": {"enabled": False}}
    
    client = MemoryClient(
        namespace=MemoryNamespace.TEST,
        config=config,
        problem_desc="test",
    )
    
    assert not client.enabled
    
    injection, ids = client.get_injection("GEN_DRAFT")
    assert injection == ""
    assert ids == []
    
    # Should not crash
    client.log_event_simple("GEN_DRAFT", None, 1.0)
