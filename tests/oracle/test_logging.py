import sqlite3
from pathlib import Path

import src.nodes.update_oracle_memory as update_oracle_memory_module
from src.memory.store import MemoryStore
from src.memory.types import MemoryEvent, MemoryItem, MemoryNamespace, Observation
from src.nodes.update_oracle_memory import update_oracle_memory_node
from src.oracle.logging import build_oracle_event_payload
from src.oracle.oracle_memory_db import OracleMemoryDB


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
        certified_count=42,
        certified_target_count=50,
        cert_ratio=0.84,
        checker_fallback_used=True,
        solver_attempt_count=3,
        selected_template_name="Top-down Memoized DP",
        prompt_char_stats={"solver": 4096},
        compact_retry_count=1,
        memory_mode="oracle",
        policy_version="rule_v1",
        candidate_action_set=["recipe.dp.memo_default"],
        selected_action="recipe.dp.memo_default",
        exploration_flag=False,
    )
    assert payload["candidate_family_pool"] == ["oracle.dp.topdown", "oracle.graph.dfs"]
    assert payload["propensity"] == 0.5
    assert payload["artifact_kind"] == "expected_output"
    assert payload["certified_count"] == 42
    assert payload["checker_fallback_used"] is True
    assert payload["prompt_char_stats"] == {"solver": 4096}
    assert payload["memory_mode"] == "oracle"
    assert payload["policy_version"] == "rule_v1"
    assert payload["selected_action"] == "recipe.dp.memo_default"
    assert payload["candidate_action_set"] == ["recipe.dp.memo_default"]
    assert payload["exploration_flag"] is False


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
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        "raw_problem": {
            "problem_id": "demo-problem",
            "public_tests": [{"input": "2\n", "output": "2\n"}],
        },
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "demo", "canonical": {"tags": ["dp"]}},
        "oracle_memory_item_ids": ["oracle.dp.topdown"],
        "tests": {
            "pass_rate": 1.0,
            "total_tests": 1,
            "test_results": [],
            "oracle_compile_success": True,
            "oracle_public_self_check_pass": True,
            "oracle_probe_pack_pass": True,
            "selected_template_name": "Top-down Memoized DP",
            "candidate_family_pool": ["oracle.dp.topdown"],
            "generated_tests": [{"input": "1\n", "output": "1\n"}],
        },
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.topdown"],
            "propensity": 1.0,
            "artifact_kind": "expected_output",
            "certified_count": 42,
            "certified_target_count": 50,
            "cert_ratio": 0.84,
            "failure_stage": "",
            "checker_fallback_used": False,
            "memory_mode": "oracle",
            "policy_version": "rule_v1",
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
            "exploration_flag": False,
            "decision": "accept",
            "reward_reason": "fully_certified",
            "cost": {"llm_calls": 2},
        },
        "oracle_memory_decision": {
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
        },
    }
    update_oracle_memory_node(state)
    store = MemoryStore(MemoryNamespace.ORACLE, tmp_path)
    store.initialize()
    events = store.get_events(limit=1)
    assert events[0].metadata["artifact_kind"] == "expected_output"
    assert events[0].metadata["certified_count"] == 42
    assert events[0].metadata["certified_target_count"] == 50
    assert events[0].metadata["cert_ratio"] == 0.84

    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()
    observations = db.list_observations()
    assert len(observations) == 1
    assert observations[0]["memory_mode"] == "oracle"
    assert observations[0]["policy_version"] == "rule_v1"
    assert observations[0]["action_bucket"] == "recipe.dp.memo_default"
    assert observations[0]["candidate_action_set_json"] == ["recipe.dp.memo_default"]
    assert observations[0]["selected_action"] == "recipe.dp.memo_default"
    assert observations[0]["selected_action_propensity"] == 1.0
    assert observations[0]["exploration_flag"] is False
    assert observations[0]["template_name"] == "Top-down Memoized DP"
    assert observations[0]["seed_family"] == "oracle.dp.topdown"
    assert observations[0]["decision"] == "accept"
    assert observations[0]["reward"] == 1.0
    assert observations[0]["reward_reason"] == "fully_certified"
    assert observations[0]["compile_success"] is True
    assert observations[0]["public_self_check_pass"] is True
    assert observations[0]["probe_pack_pass"] is True
    assert observations[0]["certified_count"] == 42
    assert observations[0]["certified_target_count"] == 50
    assert observations[0]["llm_calls"] == 2
    assert observations[0]["visible_features_snapshot_json"]["description"] == "demo"
    assert observations[0]["visible_features_snapshot_json"]["tags"] == ["dp"]
    assert observations[0]["visible_features_snapshot_json"]["test_case"] == [{"input": "2\n", "output": "2\n"}]
    assert observations[0]["visible_features_snapshot_json"]["test_case"] != [{"input": "1\n", "output": "1\n"}]


def test_update_oracle_memory_migrates_legacy_oracle_observations_table(tmp_path: Path):
    db_path = tmp_path / "oracle" / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE oracle_observations (
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id TEXT,
                problem_fingerprint TEXT,
                run_id TEXT,
                trial_id TEXT,
                action_bucket TEXT,
                candidate_action_set_json TEXT NOT NULL,
                selected_action TEXT,
                selected_action_propensity REAL,
                exploration_flag INTEGER NOT NULL,
                template_name TEXT,
                seed_family TEXT,
                visible_features_snapshot_json TEXT NOT NULL,
                decision TEXT,
                reward REAL,
                compile_success INTEGER NOT NULL,
                public_self_check_pass INTEGER NOT NULL,
                probe_pack_pass INTEGER NOT NULL,
                source_event_timestamp TEXT,
                created_at TEXT
            )
            """
        )

    state = {
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        "raw_problem": {
            "problem_id": "legacy-problem",
            "public_tests": [{"input": "2\n", "output": "2\n"}],
        },
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "legacy demo", "canonical": {"tags": ["dp"]}},
        "oracle_memory_item_ids": ["oracle.dp.topdown"],
        "tests": {
            "pass_rate": 1.0,
            "total_tests": 1,
            "test_results": [],
            "oracle_compile_success": True,
            "oracle_public_self_check_pass": True,
            "oracle_probe_pack_pass": True,
            "selected_template_name": "Top-down Memoized DP",
            "candidate_family_pool": ["oracle.dp.topdown"],
        },
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.topdown"],
            "propensity": 1.0,
            "memory_mode": "oracle",
            "policy_version": "rule_v1",
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
            "exploration_flag": False,
            "decision": "accept",
            "reward_reason": "fully_certified",
            "cost": {"llm_calls": 2},
        },
        "oracle_memory_decision": {
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
        },
    }

    update_oracle_memory_node(state)

    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()
    observations = db.list_observations()
    assert len(observations) == 1
    assert observations[0]["memory_mode"] == "oracle"
    assert observations[0]["reward_reason"] == "fully_certified"


def test_update_oracle_memory_normalized_seed_family_prefers_selected_family(tmp_path: Path):
    state = {
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        "raw_problem": {"problem_id": "demo-problem", "public_tests": []},
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "demo", "canonical": {}},
        "oracle_memory_item_ids": ["oracle.dp.topdown"],
        "tests": {
            "pass_rate": 1.0,
            "total_tests": 1,
            "test_results": [],
            "oracle_compile_success": True,
            "oracle_public_self_check_pass": True,
            "oracle_probe_pack_pass": True,
            "selected_template_name": "Top-down Memoized DP",
            "oracle_selected_family_id": "oracle.graph.fallback",
            "candidate_family_pool": ["oracle.dp.primary", "oracle.graph.fallback"],
        },
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.primary", "oracle.graph.fallback"],
            "propensity": 1.0,
            "memory_mode": "oracle",
            "policy_version": "rule_v1",
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
            "exploration_flag": False,
            "decision": "accept",
            "cost": {"llm_calls": 1},
        },
        "oracle_memory_decision": {
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
        },
    }

    update_oracle_memory_node(state)

    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()
    observations = db.list_observations()
    assert len(observations) == 1
    assert observations[0]["seed_family"] == "oracle.graph.fallback"


def test_update_oracle_memory_normalized_reward_reason_falls_back_when_metadata_blank(tmp_path: Path):
    state = {
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        "raw_problem": {"problem_id": "demo-problem", "public_tests": []},
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "demo", "canonical": {}},
        "oracle_memory_item_ids": ["oracle.dp.topdown"],
        "tests": {
            "pass_rate": 0.0,
            "total_tests": 1,
            "test_results": [{"ok": False}],
        },
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.topdown"],
            "propensity": 1.0,
            "memory_mode": "oracle",
            "policy_version": "rule_v1",
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
            "exploration_flag": False,
            "decision": "reject",
            "reward_reason": "",
            "cost": {"llm_calls": 1},
        },
        "oracle_memory_decision": {
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
        },
    }

    update_oracle_memory_node(state)

    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()
    observations = db.list_observations()
    assert len(observations) == 1
    assert observations[0]["reward_reason"] == "ALL_FAIL"


def test_update_oracle_memory_visible_tags_fall_back_to_raw_problem_tags(tmp_path: Path):
    state = {
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        "raw_problem": {
            "problem_id": "demo-problem",
            "public_tests": [],
            "tags": ["graphs", "dfs"],
        },
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "demo", "canonical": {}},
        "oracle_memory_item_ids": ["oracle.dp.topdown"],
        "tests": {
            "pass_rate": 1.0,
            "total_tests": 1,
            "test_results": [],
        },
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.topdown"],
            "propensity": 1.0,
            "memory_mode": "oracle",
            "policy_version": "rule_v1",
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
            "exploration_flag": False,
            "decision": "accept",
            "cost": {"llm_calls": 1},
        },
        "oracle_memory_decision": {
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
        },
    }

    update_oracle_memory_node(state)

    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()
    observations = db.list_observations()
    assert len(observations) == 1
    assert observations[0]["visible_features_snapshot_json"]["tags"] == ["graphs", "dfs"]


def test_update_oracle_memory_normalized_db_sink_is_best_effort(tmp_path: Path, monkeypatch):
    state = {
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        "raw_problem": {"problem_id": "demo-problem", "public_tests": []},
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "demo", "canonical": {}},
        "oracle_memory_item_ids": ["oracle.dp.topdown"],
        "tests": {"pass_rate": 1.0, "total_tests": 1, "test_results": []},
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.topdown"],
            "propensity": 1.0,
            "artifact_kind": "expected_output",
            "memory_mode": "oracle",
            "policy_version": "rule_v1",
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
            "exploration_flag": False,
            "decision": "accept",
            "cost": {"llm_calls": 1},
        },
        "oracle_memory_decision": {
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
        },
    }

    class FailingOracleMemoryDB:
        def initialize(self):
            return None

        def insert_observation_from_state(self, **kwargs):
            raise RuntimeError("normalized sink failed")

    monkeypatch.setattr(
        update_oracle_memory_module.OracleMemoryDB,
        "from_data_dir",
        classmethod(lambda cls, data_dir: FailingOracleMemoryDB()),
    )

    result = update_oracle_memory_node(state)

    assert result["execution_log"] == ["Oracle memory updated: reward=1.00 for 1 items"]
    store = MemoryStore(MemoryNamespace.ORACLE, tmp_path)
    store.initialize()
    events = store.get_events(limit=1)
    assert len(events) == 1
    assert events[0].metadata["artifact_kind"] == "expected_output"


def test_update_oracle_memory_settles_reward_only_for_selected_family_item(tmp_path: Path):
    store = MemoryStore(MemoryNamespace.ORACLE, tmp_path)
    store.initialize()
    store.add_item(
        MemoryItem(
            id="oracle-primary-item",
            namespace=MemoryNamespace.ORACLE,
            text="Primary oracle item",
            payload={"family_id": "oracle.dp.primary"},
        )
    )
    store.add_item(
        MemoryItem(
            id="oracle-fallback-item",
            namespace=MemoryNamespace.ORACLE,
            text="Fallback oracle item",
            payload={"family_id": "oracle.graph.fallback"},
        )
    )
    store.save_items()

    state = {
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        "raw_problem": {"problem_id": "demo-problem", "public_tests": []},
        "iteration": 0,
        "status": "pending",
        "problem": {"description": "demo", "canonical": {}},
        "oracle_memory_item_ids": ["oracle-primary-item", "oracle-fallback-item"],
        "tests": {
            "pass_rate": 1.0,
            "total_tests": 1,
            "test_results": [],
            "oracle_selected_family_id": "oracle.graph.fallback",
        },
        "oracle_event_metadata": {
            "candidate_family_pool": ["oracle.dp.primary", "oracle.graph.fallback"],
            "propensity": 1.0,
            "artifact_kind": "expected_output",
            "memory_mode": "oracle",
            "policy_version": "rule_v1",
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
            "exploration_flag": False,
            "decision": "accept",
            "cost": {"llm_calls": 1},
        },
        "oracle_memory_decision": {
            "selected_action": "recipe.dp.memo_default",
            "candidate_action_set": ["recipe.dp.memo_default"],
        },
    }

    update_oracle_memory_node(state)

    events = store.get_events(limit=1)
    assert len(events) == 1
    assert events[0].selected_item_ids == ["oracle-fallback-item"]
