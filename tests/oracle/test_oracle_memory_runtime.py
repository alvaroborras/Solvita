from pathlib import Path

from src.oracle.oracle_memory_db import OracleMemoryDB
from src.oracle.oracle_memory_runtime import decide_oracle_memory_gate


def test_decide_oracle_memory_gate_off_mode_is_noop(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()

    decision = decide_oracle_memory_gate(
        config={
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "off",
            }
        },
        selected_template_name="Top-down Memoized DP",
        db=db,
    )

    assert decision["applied"] is False
    assert decision["reason"] == "memory_mode_off"
    assert decision["selected_action"] == "recipe.dp.memo_default"
    assert decision["replacement_action"] is None


def test_decide_oracle_memory_gate_never_invents_new_primary_action(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()
    db.insert_observation(
        {
            "problem_id": "p1",
            "problem_fingerprint": "fp-1",
            "run_id": "run-1",
            "trial_id": "trial-1",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.dp.memo_default",
            "candidate_action_set_json": ["recipe.dp.memo_default"],
            "selected_action": "recipe.dp.memo_default",
            "selected_action_propensity": 1.0,
            "exploration_flag": False,
            "template_name": "Top-down Memoized DP",
            "seed_family": "oracle.dp.topdown",
            "visible_features_snapshot_json": {
                "description": "dp problem",
                "tags": ["dp"],
                "test_case": [{"input": "1\n", "output": "1\n"}],
            },
            "decision": "reject",
            "reward": 0.0,
            "reward_reason": "negative_reward",
            "compile_success": True,
            "public_self_check_pass": True,
            "probe_pack_pass": False,
            "certified_count": 0,
            "certified_target_count": 1,
            "llm_calls": 1,
            "token_cost": 0.01,
            "source_event_timestamp": "2026-03-28T10:00:00Z",
            "created_at": "2026-03-28T10:00:01Z",
        }
    )
    db.rebuild(snapshot_id="snapshot-test")

    decision = decide_oracle_memory_gate(
        config={
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
                "oracle_memory_snapshot_id": "snapshot-test",
            }
        },
        selected_template_name="Top-down Memoized DP",
        db=db,
    )

    assert decision["selected_action"] == "recipe.dp.memo_default"
    assert decision["replacement_action"] is None
    assert decision["candidate_action_set"] == ["recipe.dp.memo_default"]
    assert decision["reason"] == "low_confidence_selected_action"
    assert decision["stats"]["support_count"] == 1
    assert decision["stats"]["observed_success_rate"] == 0.0


def test_decide_oracle_memory_gate_missing_db_is_side_effect_free(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)

    decision = decide_oracle_memory_gate(
        config={
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
                "oracle_memory_snapshot_id": "snapshot-test",
            }
        },
        selected_template_name="Top-down Memoized DP",
        db=db,
    )

    assert decision["applied"] is False
    assert decision["reason"] == "no_snapshot_available"
    assert decision["snapshot_id"] is None
    assert not db.db_path.exists()


def test_decide_oracle_memory_gate_requires_explicit_snapshot_id(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()
    db.insert_observation(
        {
            "problem_id": "p1",
            "problem_fingerprint": "fp-1",
            "run_id": "run-1",
            "trial_id": "trial-1",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.dp.memo_default",
            "candidate_action_set_json": ["recipe.dp.memo_default"],
            "selected_action": "recipe.dp.memo_default",
            "selected_action_propensity": 1.0,
            "exploration_flag": False,
            "template_name": "Top-down Memoized DP",
            "seed_family": "oracle.dp.topdown",
            "visible_features_snapshot_json": {
                "description": "dp problem",
                "tags": ["dp"],
                "test_case": [{"input": "1\n", "output": "1\n"}],
            },
            "decision": "accept",
            "reward": 1.0,
            "reward_reason": "fully_certified",
            "compile_success": True,
            "public_self_check_pass": True,
            "probe_pack_pass": True,
            "certified_count": 1,
            "certified_target_count": 1,
            "llm_calls": 1,
            "token_cost": 0.01,
            "source_event_timestamp": "2026-03-28T10:00:00Z",
            "created_at": "2026-03-28T10:00:01Z",
        }
    )
    db.rebuild(snapshot_id="snapshot-z")

    decision = decide_oracle_memory_gate(
        config={
            "trainable_memory": {
                "enabled": True,
                "data_dir": str(tmp_path),
                "oracle_memory_mode": "oracle",
            }
        },
        selected_template_name="Top-down Memoized DP",
        db=db,
    )

    assert decision["applied"] is False
    assert decision["reason"] == "no_snapshot_available"
    assert decision["snapshot_id"] is None
    assert decision["stats"] is None
