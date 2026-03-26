from pathlib import Path

from src.memory.store import MemoryStore
from src.memory.types import MemoryEvent, MemoryNamespace, Observation
from src.nodes.update_oracle_memory import update_oracle_memory_node
from src.oracle.logging import build_oracle_event_payload


def test_oracle_event_payload_contains_ope_fields():
    payload = build_oracle_event_payload(
        problem_hash="abc",
        trainability_class="exact_single_answer",
        candidate_family_pool=["oracle.dp.topdown", "oracle.graph.dfs"],
        selected_family_ids=["oracle.dp.topdown"],
        selector_version="rule_v1",
        propensity=0.5,
        certification_route="exact_single_answer",
        verifier_provenance=None,
        decision="accept",
        artifact_kind="expected_output",
        cost={"llm_calls": 2},
    )
    assert payload["candidate_family_pool"] == ["oracle.dp.topdown", "oracle.graph.dfs"]
    assert payload["propensity"] == 0.5
    assert payload["artifact_kind"] == "expected_output"


def test_memory_event_metadata_round_trip(tmp_path: Path):
    store = MemoryStore(MemoryNamespace.ORACLE, tmp_path)
    store.initialize()
    event = MemoryEvent(
        timestamp="2026-03-26T00:00:00",
        namespace=MemoryNamespace.ORACLE,
        observation=Observation(
            fsm_state="ORACLE_SETTLE",
            raw_problem_desc="demo",
        ),
        selected_item_ids=["oracle.dp.topdown"],
        reward=1.0,
        metadata={
            "candidate_family_pool": ["oracle.dp.topdown", "oracle.graph.all_paths"],
            "propensity": 0.5,
            "artifact_kind": "expected_output",
        },
    )
    store.log_event(event)
    events = store.get_events(limit=1)
    assert events[0].metadata["candidate_family_pool"] == ["oracle.dp.topdown", "oracle.graph.all_paths"]
    assert events[0].metadata["propensity"] == 0.5


def test_update_oracle_memory_persists_metadata_round_trip(tmp_path: Path):
    state = {
        "config": {"trainable_memory": {"enabled": True, "data_dir": str(tmp_path)}},
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "demo", "canonical": {}},
        "oracle_memory_item_ids": ["oracle.dp.topdown"],
        "tests": {"pass_rate": 1.0, "total_tests": 1, "test_results": []},
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.topdown"],
            "propensity": 1.0,
            "artifact_kind": "expected_output",
        },
    }
    update_oracle_memory_node(state)
    store = MemoryStore(MemoryNamespace.ORACLE, tmp_path)
    store.initialize()
    events = store.get_events(limit=1)
    assert events[0].metadata["artifact_kind"] == "expected_output"
