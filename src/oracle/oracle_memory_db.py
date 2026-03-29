from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.oracle.oracle_memory_policy import (
    compute_description_statistics,
    compute_test_case_statistics,
    load_oracle_memory_policy_model_from_payload,
    predict_oracle_memory_policy,
    recipe_bucket_from_template_name,
    serialize_oracle_memory_policy_model,
    summarize_prediction_rows,
    train_oracle_memory_policy_from_examples,
)


JSON_FIELDS = ("candidate_action_set_json", "visible_features_snapshot_json")
BOOL_FIELDS = (
    "exploration_flag",
    "compile_success",
    "public_self_check_pass",
    "probe_pack_pass",
)
TRUE_STRINGS = {"1", "true", "t", "yes", "y", "on"}
FALSE_STRINGS = {"0", "false", "f", "no", "n", "off", ""}
DEFAULT_HOLDOUT_ECE_THRESHOLD = 0.15
DEFAULT_HOLDOUT_BRIER_THRESHOLD = 0.25
DEFAULT_HOLDOUT_MIN_EXAMPLES = 2


def _coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [part.strip() for part in text.split("|") if part.strip()]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()] if str(parsed).strip() else []
    return [str(value).strip()] if str(value).strip() else []


def _derive_action_id(observation: dict[str, Any]) -> str:
    selected_template_name = str(observation.get("template_name") or "").strip()
    action_id = str(
        observation.get("selected_action")
        or observation.get("action_bucket")
        or recipe_bucket_from_template_name(selected_template_name)
    ).strip()
    return action_id


def observations_to_training_examples(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for observation in observations:
        visible = observation.get("visible_features_snapshot_json") or {}
        description = str(visible.get("description") or "")
        tags = _coerce_tags(visible.get("tags"))
        test_cases = visible.get("test_case")
        normalized_test_cases = test_cases if isinstance(test_cases, list) else []
        selected_template_name = str(observation.get("template_name") or "").strip()
        recipe_bucket = _derive_action_id(observation)
        examples.append(
            {
                "problem_id": str(observation.get("problem_id") or ""),
                "source_path": str(observation.get("run_id") or ""),
                "selected_template_name": selected_template_name,
                "recipe_bucket": recipe_bucket or recipe_bucket_from_template_name(selected_template_name),
                "decision": str(observation.get("decision") or ""),
                "reward_reason": str(observation.get("reward_reason") or ""),
                "is_success": int(str(observation.get("decision") or "") == "accept"),
                "is_fully_certified": int(str(observation.get("reward_reason") or "") == "fully_certified"),
                "description": description,
                "tags": tags,
                "description_stats": compute_description_statistics(description),
                "test_case_stats": compute_test_case_statistics(normalized_test_cases),
                "visible_context": {
                    "problem_id": str(observation.get("problem_id") or ""),
                    "description": description,
                    "tags": tags,
                    "test_case_stats": compute_test_case_statistics(normalized_test_cases),
                },
            }
        )
    return examples


def build_action_stats_rows(
    *,
    snapshot_id: str,
    observations: list[dict[str, Any]],
    oof_predictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    support_counts = Counter()
    success_counts = Counter()
    fully_certified_counts = Counter()
    for observation in observations:
        action_id = _derive_action_id(observation)
        if not action_id:
            continue
        support_counts[action_id] += 1
        success_counts[action_id] += int(str(observation.get("decision") or "") == "accept")
        fully_certified_counts[action_id] += int(str(observation.get("reward_reason") or "") == "fully_certified")

    predicted_probabilities: dict[str, list[float]] = defaultdict(list)
    for row in oof_predictions:
        predicted_probabilities[str(row["recipe_bucket"])].append(float(row["predicted_success_probability"]))

    rows = []
    for action_id in sorted(support_counts):
        support_count = support_counts[action_id]
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "action_id": action_id,
                "stats": {
                    "support_count": support_count,
                    "success_count": success_counts[action_id],
                    "fully_certified_count": fully_certified_counts[action_id],
                    "observed_success_rate": success_counts[action_id] / support_count if support_count else 0.0,
                    "observed_fully_certified_rate": (
                        fully_certified_counts[action_id] / support_count if support_count else 0.0
                    ),
                    "mean_predicted_success_probability": (
                        sum(predicted_probabilities[action_id]) / len(predicted_probabilities[action_id])
                        if predicted_probabilities[action_id]
                        else 0.0
                    ),
                },
            }
        )
    return rows


@dataclass(frozen=True)
class OracleMemoryDB:
    db_path: Path

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> "OracleMemoryDB":
        return cls(db_path=Path(data_dir) / "oracle" / "memory.db")

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oracle_observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem_id TEXT,
                    problem_fingerprint TEXT,
                    run_id TEXT,
                    trial_id TEXT,
                    memory_mode TEXT,
                    policy_version TEXT,
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
                    reward_reason TEXT,
                    compile_success INTEGER NOT NULL,
                    public_self_check_pass INTEGER NOT NULL,
                    probe_pack_pass INTEGER NOT NULL,
                    certified_count INTEGER,
                    certified_target_count INTEGER,
                    llm_calls INTEGER,
                    token_cost REAL,
                    source_event_timestamp TEXT,
                    created_at TEXT
                )
                """
            )
            self._ensure_observations_schema(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oracle_action_stats (
                    snapshot_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    stats_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (snapshot_id, action_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oracle_model_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    model_kind TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    training_metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            self._ensure_action_stats_schema(conn)
            self._ensure_model_snapshot_schema(conn)

    def list_tables(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
                """
            ).fetchall()
        return [row[0] for row in rows]

    def insert_observation(self, row: dict[str, Any]) -> int:
        encoded = dict(row)
        for field in JSON_FIELDS:
            encoded[field] = json.dumps(encoded[field])
        for field in BOOL_FIELDS:
            encoded[field] = int(self._coerce_bool(encoded[field]))

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO oracle_observations (
                    problem_id,
                    problem_fingerprint,
                    run_id,
                    trial_id,
                    memory_mode,
                    policy_version,
                    action_bucket,
                    candidate_action_set_json,
                    selected_action,
                    selected_action_propensity,
                    exploration_flag,
                    template_name,
                    seed_family,
                    visible_features_snapshot_json,
                    decision,
                    reward,
                    reward_reason,
                    compile_success,
                    public_self_check_pass,
                    probe_pack_pass,
                    certified_count,
                    certified_target_count,
                    llm_calls,
                    token_cost,
                    source_event_timestamp,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    encoded.get("problem_id"),
                    encoded.get("problem_fingerprint"),
                    encoded.get("run_id"),
                    encoded.get("trial_id"),
                    encoded.get("memory_mode"),
                    encoded.get("policy_version"),
                    encoded.get("action_bucket"),
                    encoded["candidate_action_set_json"],
                    encoded.get("selected_action"),
                    encoded.get("selected_action_propensity"),
                    encoded["exploration_flag"],
                    encoded.get("template_name"),
                    encoded.get("seed_family"),
                    encoded["visible_features_snapshot_json"],
                    encoded.get("decision"),
                    encoded.get("reward"),
                    encoded.get("reward_reason"),
                    encoded["compile_success"],
                    encoded["public_self_check_pass"],
                    encoded["probe_pack_pass"],
                    encoded.get("certified_count"),
                    encoded.get("certified_target_count"),
                    encoded.get("llm_calls"),
                    encoded.get("token_cost"),
                    encoded.get("source_event_timestamp"),
                    encoded.get("created_at"),
                ),
            )
        return int(cursor.lastrowid)

    def get_observation(self, observation_id: int) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM oracle_observations
                WHERE observation_id = ?
                """,
                (observation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._decode_observation(row)

    def list_observations(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT *
                FROM oracle_observations
                ORDER BY observation_id
                """
            ).fetchall()
        return [self._decode_observation(row) for row in rows]

    def insert_observation_from_state(
        self,
        state: dict[str, Any],
        reward: float,
        failure_type: str | None,
        iteration: int,
    ) -> int:
        metadata = state.get("oracle_event_metadata", {}) or {}
        decision = state.get("oracle_memory_decision", {}) or {}
        tests = state.get("tests", {}) or {}
        problem = state.get("problem", {}) or {}
        canonical = problem.get("canonical", {}) or {}
        problem_desc = str(problem.get("description", "") or "")
        selected_action = str(
            metadata.get("selected_action")
            or decision.get("selected_action")
            or ""
        )
        candidate_action_set = metadata.get("candidate_action_set")
        if candidate_action_set is None:
            candidate_action_set = decision.get("candidate_action_set")
        candidate_action_set = list(candidate_action_set or [])
        cost = metadata.get("cost", {}) or {}
        timestamp = datetime.now(timezone.utc).isoformat()
        raw_problem = state.get("raw_problem", {}) or {}
        problem_id = (
            canonical.get("problem_id")
            or canonical.get("id")
            or raw_problem.get("problem_id")
            or raw_problem.get("id")
        )
        reward_reason = str(metadata.get("reward_reason") or "").strip()
        if not reward_reason:
            reward_reason = "success" if reward >= 1.0 else str(failure_type or "")
        selected_family = tests.get("oracle_selected_family_id")
        seed_family = str(selected_family) if selected_family else None
        candidate_family_pool = metadata.get("candidate_family_pool")
        if candidate_family_pool is None:
            candidate_family_pool = tests.get("candidate_family_pool", [])
        candidate_family_pool = list(candidate_family_pool or [])
        if seed_family is None and candidate_family_pool:
            seed_family = str(candidate_family_pool[0])
        visible_test_case = raw_problem.get("test_case")
        if visible_test_case is None:
            visible_test_case = raw_problem.get("public_tests", [])

        row = {
            "problem_id": problem_id,
            "problem_fingerprint": metadata.get("problem_hash") or hashlib.md5(problem_desc.encode("utf-8")).hexdigest(),
            "run_id": state.get("run_id"),
            "trial_id": str(state.get("trial_id") or f"iteration-{iteration}"),
            "memory_mode": metadata.get("memory_mode") or decision.get("memory_mode") or "off",
            "policy_version": metadata.get("policy_version") or decision.get("policy_version") or "rule_v1",
            "action_bucket": selected_action,
            "candidate_action_set_json": candidate_action_set,
            "selected_action": selected_action,
            "selected_action_propensity": metadata.get("propensity"),
            "exploration_flag": metadata.get("exploration_flag", decision.get("exploration_flag", False)),
            "template_name": tests.get("selected_template_name") or metadata.get("selected_template_name"),
            "seed_family": seed_family,
            "visible_features_snapshot_json": {
                "description": problem_desc,
                "tags": canonical.get("tags", []) or raw_problem.get("tags", []),
                "test_case": visible_test_case,
            },
            "decision": metadata.get("decision", ""),
            "reward": reward,
            "reward_reason": reward_reason,
            "compile_success": tests.get("oracle_compile_success", False),
            "public_self_check_pass": tests.get("oracle_public_self_check_pass", False),
            "probe_pack_pass": tests.get("oracle_probe_pack_pass", False),
            "certified_count": metadata.get("certified_count", tests.get("certified_count")),
            "certified_target_count": metadata.get("certified_target_count", tests.get("certified_target_count")),
            "llm_calls": cost.get("llm_calls"),
            "token_cost": cost.get("token_cost"),
            "source_event_timestamp": metadata.get("source_event_timestamp") or timestamp,
            "created_at": timestamp,
        }
        return self.insert_observation(row)

    def rebuild(self, snapshot_id: str) -> dict[str, Any]:
        normalized_snapshot_id = str(snapshot_id).strip()
        if not normalized_snapshot_id:
            raise ValueError("snapshot_id is required")

        observations = self.list_observations()
        examples = observations_to_training_examples(observations)
        training_metadata = {
            "snapshot_id": normalized_snapshot_id,
            "num_observations": len(observations),
            "num_examples": len(examples),
            "num_unique_problem_ids": len({example["problem_id"] for example in examples}),
        }
        training = train_oracle_memory_policy_from_examples(
            examples,
            training_metadata=training_metadata,
        )
        action_stats_rows = build_action_stats_rows(
            snapshot_id=normalized_snapshot_id,
            observations=observations,
            oof_predictions=training["oof_predictions"],
        )
        model_payload = serialize_oracle_memory_policy_model(training["model"])
        metrics = {
            "selection_summary": training["selection_summary"],
            "recipe_bucket_summary": training["recipe_bucket_summary"],
        }

        with sqlite3.connect(self.db_path) as conn:
            self._ensure_action_stats_schema(conn)
            self._ensure_model_snapshot_schema(conn)
            conn.execute(
                """
                DELETE FROM oracle_action_stats
                WHERE snapshot_id = ?
                """,
                (normalized_snapshot_id,),
            )
            conn.executemany(
                """
                INSERT INTO oracle_action_stats (
                    snapshot_id,
                    action_id,
                    stats_json
                ) VALUES (?, ?, ?)
                """,
                [
                    (row["snapshot_id"], row["action_id"], json.dumps(row["stats"], ensure_ascii=False, sort_keys=True))
                    for row in action_stats_rows
                ],
            )
            conn.execute(
                """
                INSERT INTO oracle_model_snapshots (
                    snapshot_id,
                    model_kind,
                    payload_json,
                    metrics_json,
                    training_metadata_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    model_kind = excluded.model_kind,
                    payload_json = excluded.payload_json,
                    metrics_json = excluded.metrics_json,
                    training_metadata_json = excluded.training_metadata_json
                """,
                (
                    normalized_snapshot_id,
                    "observed_action_confidence",
                    json.dumps(model_payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                    json.dumps(training_metadata, ensure_ascii=False, sort_keys=True),
                ),
            )

        return {
            "snapshot_id": normalized_snapshot_id,
            "num_observations": len(observations),
            "num_examples": len(examples),
            "model": training["model"],
            "model_payload": model_payload,
            "selection_summary": training["selection_summary"],
            "recipe_bucket_summary": training["recipe_bucket_summary"],
            "oof_predictions": training["oof_predictions"],
            "action_stats_rows": action_stats_rows,
        }

    def list_action_stats(self, snapshot_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT snapshot_id, action_id, stats_json
                FROM oracle_action_stats
                WHERE snapshot_id = ?
                ORDER BY action_id
                """,
                (snapshot_id,),
            ).fetchall()
        return [
            {
                "snapshot_id": str(row["snapshot_id"]),
                "action_id": str(row["action_id"]),
                "stats": json.loads(row["stats_json"]),
            }
            for row in rows
        ]

    def get_model_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT snapshot_id, model_kind, payload_json, metrics_json, training_metadata_json
                FROM oracle_model_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        model = None
        required_model_fields = {"feature_names", "weights", "numeric_stats"}
        if required_model_fields <= set(payload):
            model = load_oracle_memory_policy_model_from_payload(payload)
        return {
            "snapshot_id": str(row["snapshot_id"]),
            "model_kind": str(row["model_kind"]),
            "payload": payload,
            "metrics": json.loads(row["metrics_json"]),
            "training_metadata": json.loads(row["training_metadata_json"]),
            "model": model,
        }

    def evaluate_holdout(self, snapshot_id: str, holdout_examples: list[dict[str, Any]]) -> dict[str, Any]:
        normalized_snapshot_id = str(snapshot_id).strip()
        if not normalized_snapshot_id:
            raise ValueError("snapshot_id is required")

        snapshot = self.get_model_snapshot(normalized_snapshot_id)
        if snapshot is None:
            raise ValueError(f"unknown snapshot_id: {normalized_snapshot_id}")

        payload = snapshot["payload"]
        required_model_fields = {"feature_names", "weights", "numeric_stats"}
        if not required_model_fields <= set(payload):
            raise ValueError(f"snapshot_id does not contain a stored model payload: {normalized_snapshot_id}")
        model = load_oracle_memory_policy_model_from_payload(payload)
        probabilities = predict_oracle_memory_policy(model, holdout_examples)
        prediction_rows = [
            {
                "problem_id": example["problem_id"],
                "recipe_bucket": example["recipe_bucket"],
                "selected_template_name": example["selected_template_name"],
                "decision": example["decision"],
                "reward_reason": example["reward_reason"],
                "is_success": int(example["is_success"]),
                "is_fully_certified": int(example["is_fully_certified"]),
                "predicted_success_probability": float(probability),
                "predicted_success_label": int(probability >= model.success_threshold),
            }
            for example, probability in zip(holdout_examples, probabilities)
        ]
        external_holdout_metrics = summarize_prediction_rows(
            prediction_rows,
            success_threshold=model.success_threshold,
        )
        accept_prediction_metrics = external_holdout_metrics["observed_action_metrics"]["accept_prediction"]
        num_examples = int(accept_prediction_metrics["num_examples"])
        has_minimum_evidence = num_examples >= DEFAULT_HOLDOUT_MIN_EXAMPLES
        calibration_gate = {
            "metric_name": "accept_prediction",
            "num_examples": num_examples,
            "min_examples_required": DEFAULT_HOLDOUT_MIN_EXAMPLES,
            "ece": float(accept_prediction_metrics["ece"]),
            "brier_score": float(accept_prediction_metrics["brier_score"]),
            "ece_threshold": DEFAULT_HOLDOUT_ECE_THRESHOLD,
            "brier_score_threshold": DEFAULT_HOLDOUT_BRIER_THRESHOLD,
            "reason": None,
        }
        calibration_gate["passed"] = (
            has_minimum_evidence
            and calibration_gate["ece"] <= calibration_gate["ece_threshold"]
            and calibration_gate["brier_score"] <= calibration_gate["brier_score_threshold"]
        )
        if not has_minimum_evidence:
            calibration_gate["reason"] = "insufficient_holdout_examples"
        elif not (
            calibration_gate["ece"] <= calibration_gate["ece_threshold"]
            and calibration_gate["brier_score"] <= calibration_gate["brier_score_threshold"]
        ):
            calibration_gate["reason"] = "calibration_threshold_failed"
        runtime_readiness = {
            "state": "holdout_gate_only" if calibration_gate["passed"] else "offline_only",
            "calibration_gate_passed": bool(calibration_gate["passed"]),
            "runtime_hook_integrated": False,
        }
        return {
            "snapshot_id": normalized_snapshot_id,
            "selection_metrics": dict(snapshot["metrics"].get("selection_summary") or {}),
            "external_holdout_metrics": external_holdout_metrics,
            "calibration_gate": calibration_gate,
            "runtime_readiness": runtime_readiness,
            "prediction_rows": prediction_rows,
        }

    def _decode_observation(self, row: sqlite3.Row) -> dict[str, Any]:
        decoded = dict(row)
        for field in JSON_FIELDS:
            decoded[field] = json.loads(decoded[field])
        for field in BOOL_FIELDS:
            decoded[field] = bool(decoded[field])
        return decoded

    def _coerce_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in TRUE_STRINGS:
                return True
            if normalized in FALSE_STRINGS:
                return False
        return bool(value)

    def _ensure_observations_schema(self, conn: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(oracle_observations)").fetchall()
        }
        required_columns = (
            ("memory_mode", "TEXT"),
            ("policy_version", "TEXT"),
            ("reward_reason", "TEXT"),
            ("certified_count", "INTEGER"),
            ("certified_target_count", "INTEGER"),
            ("llm_calls", "INTEGER"),
            ("token_cost", "REAL"),
        )
        for column_name, column_type in required_columns:
            if column_name in columns:
                continue
            conn.execute(f"ALTER TABLE oracle_observations ADD COLUMN {column_name} {column_type}")

    def _ensure_action_stats_schema(self, conn: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(oracle_action_stats)").fetchall()
        }
        if {"snapshot_id", "action_id", "stats_json"} <= columns:
            return
        legacy_rows = conn.execute("SELECT action_id, stats_json FROM oracle_action_stats").fetchall()
        conn.execute("ALTER TABLE oracle_action_stats RENAME TO oracle_action_stats_legacy")
        conn.execute(
            """
            CREATE TABLE oracle_action_stats (
                snapshot_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                stats_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (snapshot_id, action_id)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO oracle_action_stats (snapshot_id, action_id, stats_json)
            VALUES (?, ?, ?)
            """,
            [("legacy", row[0], row[1]) for row in legacy_rows],
        )
        conn.execute("DROP TABLE oracle_action_stats_legacy")

    def _ensure_model_snapshot_schema(self, conn: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(oracle_model_snapshots)").fetchall()
        }
        if {"snapshot_id", "model_kind", "payload_json", "metrics_json", "training_metadata_json"} <= columns:
            return
        legacy_rows = conn.execute("SELECT snapshot_id, metadata_json FROM oracle_model_snapshots").fetchall()
        conn.execute("ALTER TABLE oracle_model_snapshots RENAME TO oracle_model_snapshots_legacy")
        conn.execute(
            """
            CREATE TABLE oracle_model_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                model_kind TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                training_metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO oracle_model_snapshots (
                snapshot_id,
                model_kind,
                payload_json,
                metrics_json,
                training_metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [(row[0], "legacy", "{}", row[1], "{}") for row in legacy_rows],
        )
        conn.execute("DROP TABLE oracle_model_snapshots_legacy")
