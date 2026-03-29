import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from src.oracle.oracle_memory_db import OracleMemoryDB


def test_initialize_creates_required_tables(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)

    db.initialize()

    assert db.db_path == tmp_path / "oracle" / "memory.db"
    assert set(db.list_tables()) >= {
        "oracle_observations",
        "oracle_action_stats",
        "oracle_model_snapshots",
    }

    with sqlite3.connect(db.db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(oracle_observations)").fetchall()
        }

    assert columns >= {
        "observation_id",
        "problem_id",
        "problem_fingerprint",
        "run_id",
        "trial_id",
        "memory_mode",
        "policy_version",
        "action_bucket",
        "candidate_action_set_json",
        "selected_action",
        "selected_action_propensity",
        "exploration_flag",
        "template_name",
        "seed_family",
        "visible_features_snapshot_json",
        "decision",
        "reward",
        "reward_reason",
        "compile_success",
        "public_self_check_pass",
        "probe_pack_pass",
        "certified_count",
        "certified_target_count",
        "llm_calls",
        "token_cost",
        "source_event_timestamp",
        "created_at",
    }


def test_insert_observation_returns_integer_id_and_round_trips_plan_spine_fields(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()

    row = {
        "problem_id": "two-sum",
        "problem_fingerprint": "sha256:abc123",
        "run_id": "run-123",
        "trial_id": "trial-007",
        "memory_mode": "oracle",
        "policy_version": "v1",
        "action_bucket": "template.dp",
        "candidate_action_set_json": [
            {"action": "template.dp.memo", "score": 0.625},
            {"action": "template.graph.bfs", "score": 0.375},
        ],
        "selected_action": "template.dp.memo",
        "selected_action_propensity": 0.625,
        "exploration_flag": True,
        "template_name": "Top-down Memoized DP",
        "seed_family": "dp.memo",
        "visible_features_snapshot_json": {
            "problem_tags": ["dp", "arrays"],
            "num_tests": 3,
        },
        "decision": "accept",
        "reward": 1.0,
        "reward_reason": "fully_certified",
        "compile_success": False,
        "public_self_check_pass": True,
        "probe_pack_pass": False,
        "certified_count": 8,
        "certified_target_count": 10,
        "llm_calls": 4,
        "token_cost": 0.123,
        "source_event_timestamp": "2026-03-28T10:15:00Z",
        "created_at": "2026-03-28T10:16:00Z",
    }

    observation_id = db.insert_observation(row)

    assert isinstance(observation_id, int)
    assert observation_id > 0

    stored = db.get_observation(observation_id)
    assert stored is not None
    assert stored["observation_id"] == observation_id
    assert stored["problem_id"] == row["problem_id"]
    assert stored["problem_fingerprint"] == row["problem_fingerprint"]
    assert stored["run_id"] == row["run_id"]
    assert stored["trial_id"] == row["trial_id"]
    assert stored["memory_mode"] == row["memory_mode"]
    assert stored["policy_version"] == row["policy_version"]
    assert stored["action_bucket"] == row["action_bucket"]
    assert stored["candidate_action_set_json"] == row["candidate_action_set_json"]
    assert stored["selected_action"] == row["selected_action"]
    assert stored["selected_action_propensity"] == row["selected_action_propensity"]
    assert stored["template_name"] == row["template_name"]
    assert stored["seed_family"] == row["seed_family"]
    assert stored["visible_features_snapshot_json"] == row["visible_features_snapshot_json"]
    assert stored["decision"] == row["decision"]
    assert stored["reward"] == row["reward"]
    assert stored["reward_reason"] == row["reward_reason"]
    assert stored["exploration_flag"] is True
    assert stored["compile_success"] is False
    assert stored["public_self_check_pass"] is True
    assert stored["probe_pack_pass"] is False
    assert stored["certified_count"] == row["certified_count"]
    assert stored["certified_target_count"] == row["certified_target_count"]
    assert stored["llm_calls"] == row["llm_calls"]
    assert stored["token_cost"] == row["token_cost"]
    assert stored["source_event_timestamp"] == row["source_event_timestamp"]
    assert stored["created_at"] == row["created_at"]

    assert db.list_observations() == [stored]


def test_insert_observation_coerces_common_string_bool_values_without_corruption(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()

    observation_id = db.insert_observation(
        {
            "problem_id": "bool-case",
            "problem_fingerprint": "sha256:bools",
            "run_id": "run-bool",
            "trial_id": "trial-bool",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "template.misc",
            "candidate_action_set_json": [{"action": "template.misc", "score": 1.0}],
            "selected_action": "template.misc",
            "selected_action_propensity": 1.0,
            "exploration_flag": "false",
            "template_name": "Boolean Template",
            "seed_family": "misc",
            "visible_features_snapshot_json": {"feature": "value"},
            "decision": "accept",
            "reward": 0.5,
            "reward_reason": "manual",
            "compile_success": "0",
            "public_self_check_pass": "true",
            "probe_pack_pass": "1",
            "certified_count": 1,
            "certified_target_count": 1,
            "llm_calls": 1,
            "token_cost": 0.01,
            "source_event_timestamp": "2026-03-28T12:00:00Z",
            "created_at": "2026-03-28T12:00:01Z",
        }
    )

    stored = db.get_observation(observation_id)

    assert stored is not None
    assert stored["exploration_flag"] is False
    assert stored["compile_success"] is False
    assert stored["public_self_check_pass"] is True
    assert stored["probe_pack_pass"] is True


def test_rebuild_writes_action_stats_and_model_snapshot_for_snapshot_id(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()

    rows = [
        {
            "problem_id": "p1",
            "problem_fingerprint": "fp-1",
            "run_id": "run-1",
            "trial_id": "trial-1",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.dp.memo_default",
            "candidate_action_set_json": ["recipe.dp.memo_default", "recipe.specialized.other"],
            "selected_action": "recipe.dp.memo_default",
            "selected_action_propensity": 0.8,
            "exploration_flag": False,
            "template_name": "Top-down Memoized DP",
            "seed_family": "dp.memo",
            "visible_features_snapshot_json": {
                "description": "Dynamic programming over prefixes",
                "tags": ["dp", "arrays"],
                "test_case": [{"input": "3\n1 2 3\n", "output": "6\n"}],
            },
            "decision": "accept",
            "reward": 1.0,
            "reward_reason": "fully_certified",
            "compile_success": True,
            "public_self_check_pass": True,
            "probe_pack_pass": True,
            "certified_count": 3,
            "certified_target_count": 3,
            "llm_calls": 2,
            "token_cost": 0.11,
            "source_event_timestamp": "2026-03-28T10:00:00Z",
            "created_at": "2026-03-28T10:00:01Z",
        },
        {
            "problem_id": "p2",
            "problem_fingerprint": "fp-2",
            "run_id": "run-1",
            "trial_id": "trial-2",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.dp.memo_default",
            "candidate_action_set_json": ["recipe.dp.memo_default", "recipe.enum.simulation_default"],
            "selected_action": "recipe.dp.memo_default",
            "selected_action_propensity": 0.7,
            "exploration_flag": False,
            "template_name": "Top-down Memoized DP",
            "seed_family": "dp.memo",
            "visible_features_snapshot_json": {
                "description": "State compression with memoization",
                "tags": ["dp"],
                "test_case": [{"input": "2\n5 8\n", "output": "13\n"}],
            },
            "decision": "reject",
            "reward": 0.0,
            "reward_reason": "compile_error",
            "compile_success": False,
            "public_self_check_pass": False,
            "probe_pack_pass": False,
            "certified_count": 0,
            "certified_target_count": 3,
            "llm_calls": 3,
            "token_cost": 0.21,
            "source_event_timestamp": "2026-03-28T10:01:00Z",
            "created_at": "2026-03-28T10:01:01Z",
        },
        {
            "problem_id": "p3",
            "problem_fingerprint": "fp-3",
            "run_id": "run-1",
            "trial_id": "trial-3",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.specialized.other",
            "candidate_action_set_json": ["recipe.specialized.other", "recipe.dp.memo_default"],
            "selected_action": "recipe.specialized.other",
            "selected_action_propensity": 0.6,
            "exploration_flag": False,
            "template_name": "Greedy Counting Trick",
            "seed_family": "greedy",
            "visible_features_snapshot_json": {
                "description": "Count local transitions and greedily merge runs",
                "tags": ["greedy"],
                "test_case": [{"input": "4\nabba\n", "output": "2\n"}],
            },
            "decision": "accept",
            "reward": 1.0,
            "reward_reason": "success",
            "compile_success": True,
            "public_self_check_pass": True,
            "probe_pack_pass": False,
            "certified_count": 2,
            "certified_target_count": 3,
            "llm_calls": 2,
            "token_cost": 0.09,
            "source_event_timestamp": "2026-03-28T10:02:00Z",
            "created_at": "2026-03-28T10:02:01Z",
        },
    ]

    for row in rows:
        db.insert_observation(row)

    result = db.rebuild(snapshot_id="snapshot-2026-03-28")

    assert result["snapshot_id"] == "snapshot-2026-03-28"

    action_stats = db.list_action_stats("snapshot-2026-03-28")
    assert len(action_stats) == 2
    support_counts = {row["action_id"]: row["stats"]["support_count"] for row in action_stats}
    assert support_counts == {
        "recipe.dp.memo_default": 2,
        "recipe.specialized.other": 1,
    }

    model_snapshot = db.get_model_snapshot("snapshot-2026-03-28")
    assert model_snapshot is not None
    assert model_snapshot["snapshot_id"] == "snapshot-2026-03-28"
    assert model_snapshot["model_kind"] == "observed_action_confidence"
    assert "selection_summary" in model_snapshot["metrics"]


def test_initialize_migrates_legacy_model_snapshot_rows_without_breaking_reads(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            """
            CREATE TABLE oracle_model_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO oracle_model_snapshots (snapshot_id, metadata_json)
            VALUES (?, ?)
            """,
            ("legacy-snapshot", '{"migrated": true}'),
        )
        conn.execute(
            """
            CREATE TABLE oracle_action_stats (
                action_id TEXT PRIMARY KEY,
                stats_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )

    db.initialize()

    snapshot = db.get_model_snapshot("legacy-snapshot")

    assert snapshot is not None
    assert snapshot["snapshot_id"] == "legacy-snapshot"
    assert snapshot["model_kind"] == "legacy"
    assert snapshot["payload"] == {}
    assert snapshot["model"] is None


def test_rebuild_uses_template_bucket_fallback_for_blank_action_ids(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()

    for row in [
        {
            "problem_id": "fallback-1",
            "problem_fingerprint": "fp-fallback-1",
            "run_id": "run-fallback",
            "trial_id": "trial-fallback-1",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "",
            "candidate_action_set_json": ["recipe.dp.memo_default"],
            "selected_action": "",
            "selected_action_propensity": 1.0,
            "exploration_flag": False,
            "template_name": "Top-down Memoized DP",
            "seed_family": "dp.memo",
            "visible_features_snapshot_json": {
                "description": "Memoize transitions over indices",
                "tags": ["dp"],
                "test_case": [{"input": "1\n7\n", "output": "7\n"}],
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
            "token_cost": 0.02,
            "source_event_timestamp": "2026-03-28T11:00:00Z",
            "created_at": "2026-03-28T11:00:01Z",
        },
        {
            "problem_id": "fallback-2",
            "problem_fingerprint": "fp-fallback-2",
            "run_id": "run-fallback",
            "trial_id": "trial-fallback-2",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.specialized.other",
            "candidate_action_set_json": ["recipe.specialized.other"],
            "selected_action": "recipe.specialized.other",
            "selected_action_propensity": 1.0,
            "exploration_flag": False,
            "template_name": "Greedy Counting Trick",
            "seed_family": "greedy",
            "visible_features_snapshot_json": {
                "description": "Greedy merge of counted runs",
                "tags": ["greedy"],
                "test_case": [{"input": "2\naa\n", "output": "1\n"}],
            },
            "decision": "reject",
            "reward": 0.0,
            "reward_reason": "compile_error",
            "compile_success": False,
            "public_self_check_pass": False,
            "probe_pack_pass": False,
            "certified_count": 0,
            "certified_target_count": 1,
            "llm_calls": 1,
            "token_cost": 0.02,
            "source_event_timestamp": "2026-03-28T11:01:00Z",
            "created_at": "2026-03-28T11:01:01Z",
        },
    ]:
        db.insert_observation(row)

    db.rebuild(snapshot_id="snapshot-fallback")

    action_ids = [row["action_id"] for row in db.list_action_stats("snapshot-fallback")]

    assert "recipe.dp.memo_default" in action_ids


def test_rebuild_script_runs_directly_without_pythonpath_and_writes_artifacts(tmp_path: Path) -> None:
    db = OracleMemoryDB.from_data_dir(tmp_path)
    db.initialize()

    rows = [
        {
            "problem_id": "p1",
            "problem_fingerprint": "fp-1",
            "run_id": "run-1",
            "trial_id": "trial-1",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.dp.memo_default",
            "candidate_action_set_json": ["recipe.dp.memo_default", "recipe.specialized.other"],
            "selected_action": "recipe.dp.memo_default",
            "selected_action_propensity": 0.8,
            "exploration_flag": False,
            "template_name": "Top-down Memoized DP",
            "seed_family": "dp.memo",
            "visible_features_snapshot_json": {
                "description": "Dynamic programming over prefixes",
                "tags": ["dp", "arrays"],
                "test_case": [{"input": "3\n1 2 3\n", "output": "6\n"}],
            },
            "decision": "accept",
            "reward": 1.0,
            "reward_reason": "fully_certified",
            "compile_success": True,
            "public_self_check_pass": True,
            "probe_pack_pass": True,
            "certified_count": 3,
            "certified_target_count": 3,
            "llm_calls": 2,
            "token_cost": 0.11,
            "source_event_timestamp": "2026-03-28T10:00:00Z",
            "created_at": "2026-03-28T10:00:01Z",
        },
        {
            "problem_id": "p2",
            "problem_fingerprint": "fp-2",
            "run_id": "run-1",
            "trial_id": "trial-2",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.dp.memo_default",
            "candidate_action_set_json": ["recipe.dp.memo_default", "recipe.enum.simulation_default"],
            "selected_action": "recipe.dp.memo_default",
            "selected_action_propensity": 0.7,
            "exploration_flag": False,
            "template_name": "Top-down Memoized DP",
            "seed_family": "dp.memo",
            "visible_features_snapshot_json": {
                "description": "State compression with memoization",
                "tags": ["dp"],
                "test_case": [{"input": "2\n5 8\n", "output": "13\n"}],
            },
            "decision": "reject",
            "reward": 0.0,
            "reward_reason": "compile_error",
            "compile_success": False,
            "public_self_check_pass": False,
            "probe_pack_pass": False,
            "certified_count": 0,
            "certified_target_count": 3,
            "llm_calls": 3,
            "token_cost": 0.21,
            "source_event_timestamp": "2026-03-28T10:01:00Z",
            "created_at": "2026-03-28T10:01:01Z",
        },
        {
            "problem_id": "p3",
            "problem_fingerprint": "fp-3",
            "run_id": "run-1",
            "trial_id": "trial-3",
            "memory_mode": "oracle",
            "policy_version": "v1",
            "action_bucket": "recipe.specialized.other",
            "candidate_action_set_json": ["recipe.specialized.other", "recipe.dp.memo_default"],
            "selected_action": "recipe.specialized.other",
            "selected_action_propensity": 0.6,
            "exploration_flag": False,
            "template_name": "Greedy Counting Trick",
            "seed_family": "greedy",
            "visible_features_snapshot_json": {
                "description": "Count local transitions and greedily merge runs",
                "tags": ["greedy"],
                "test_case": [{"input": "4\nabba\n", "output": "2\n"}],
            },
            "decision": "accept",
            "reward": 1.0,
            "reward_reason": "success",
            "compile_success": True,
            "public_self_check_pass": True,
            "probe_pack_pass": False,
            "certified_count": 2,
            "certified_target_count": 3,
            "llm_calls": 2,
            "token_cost": 0.09,
            "source_event_timestamp": "2026-03-28T10:02:00Z",
            "created_at": "2026-03-28T10:02:01Z",
        },
    ]

    for row in rows:
        db.insert_observation(row)

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "rebuild_oracle_memory_db.py"
    output_dir = tmp_path / "artifacts"
    snapshot_id = "snapshot-cli"
    prefix = "oracle-memory"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--data-dir",
            str(tmp_path),
            "--snapshot-id",
            snapshot_id,
            "--output-dir",
            str(output_dir),
            "--prefix",
            prefix,
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert f'"snapshot_id": "{snapshot_id}"' in result.stdout
    assert (output_dir / f"{prefix}_selection_summary.json").exists()
    assert (output_dir / f"{prefix}_recipe_bucket_summary.json").exists()
    assert (output_dir / f"{prefix}_feature_weights.csv").exists()
    assert (output_dir / f"{prefix}_oof_predictions.csv").exists()
