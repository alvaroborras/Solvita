from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class FailureBankService:
    def __init__(self, data_dir: str | Path) -> None:
        raw_data_dir = str(data_dir or "").strip()
        self.root = Path(raw_data_dir) if raw_data_dir else None
        self.db_path = (self.root / "failure_bank.db") if self.root is not None else None
        self._ephemeral = self.root is None
        self._memory_conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> sqlite3.Connection:
        if self._ephemeral:
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:")
                self._memory_conn.row_factory = sqlite3.Row
            return self._memory_conn
        assert self.db_path is not None
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _finish(self, conn: sqlite3.Connection) -> None:
        conn.commit()
        if not self._ephemeral:
            conn.close()

    def initialize(self) -> None:
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_cases (
                    case_id TEXT PRIMARY KEY,
                    canonical_objective TEXT,
                    tags_level1_json TEXT,
                    tags_level2_json TEXT,
                    constraint_bucket TEXT,
                    phase_found TEXT,
                    failure_type TEXT,
                    failure_subtype TEXT,
                    input_text TEXT,
                    expected_output TEXT,
                    actual_output TEXT,
                    checker_context TEXT,
                    trusted_level TEXT,
                    source_run_id TEXT,
                    source_solution_hash TEXT,
                    explanation TEXT,
                    minimized INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    title TEXT,
                    applicable_tags_json TEXT,
                    trigger_features_json TEXT,
                    anti_pattern_text TEXT,
                    recommended_checks_json TEXT,
                    evidence_case_ids_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repair_outcomes (
                    repair_id TEXT PRIMARY KEY,
                    linked_case_ids_json TEXT,
                    repair_strategy TEXT,
                    repair_summary TEXT,
                    before_solution_hash TEXT,
                    after_solution_hash TEXT,
                    validated INTEGER
                )
                """
            )
        finally:
            self._finish(conn)

    def record_failure_case(self, payload: Dict[str, Any]) -> str:
        canonical_objective = str(payload.get("canonical_objective", "") or "")
        input_text = str(payload.get("input_text", "") or "")
        expected_output = str(payload.get("expected_output", "") or "")
        actual_output = str(payload.get("actual_output", "") or "")
        raw_key = json.dumps(
            [
                canonical_objective,
                input_text,
                expected_output,
                actual_output,
                str(payload.get("failure_type", "") or ""),
                str(payload.get("failure_subtype", "") or ""),
                str(payload.get("phase_found", "") or ""),
                str(payload.get("source_run_id", "") or ""),
                str(payload.get("source_solution_hash", "") or ""),
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        case_id = str(payload.get("case_id") or hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20])
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO failure_cases (
                    case_id, canonical_objective, tags_level1_json, tags_level2_json, constraint_bucket,
                    phase_found, failure_type, failure_subtype, input_text, expected_output, actual_output,
                    checker_context, trusted_level, source_run_id, source_solution_hash, explanation, minimized
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    canonical_objective,
                    json.dumps(payload.get("tags_level1", [])),
                    json.dumps(payload.get("tags_level2", [])),
                    str(payload.get("constraint_bucket", "") or ""),
                    str(payload.get("phase_found", "") or ""),
                    str(payload.get("failure_type", "") or ""),
                    str(payload.get("failure_subtype", "") or ""),
                    input_text,
                    expected_output,
                    actual_output,
                    str(payload.get("checker_context", "") or ""),
                    str(payload.get("trusted_level", "high") or "high"),
                    str(payload.get("source_run_id", "") or ""),
                    str(payload.get("source_solution_hash", "") or ""),
                    str(payload.get("explanation", "") or ""),
                    int(bool(payload.get("minimized", False))),
                ),
            )
        finally:
            self._finish(conn)
        return case_id

    def record_risk_pattern(self, payload: Dict[str, Any]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO risk_patterns (
                    pattern_id, title, applicable_tags_json, trigger_features_json,
                    anti_pattern_text, recommended_checks_json, evidence_case_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload["pattern_id"]),
                    str(payload.get("title", "")),
                    json.dumps(payload.get("applicable_tags", [])),
                    json.dumps(payload.get("trigger_features", [])),
                    str(payload.get("anti_pattern_text", "")),
                    json.dumps(payload.get("recommended_checks", [])),
                    json.dumps(payload.get("evidence_case_ids", [])),
                ),
            )
        finally:
            self._finish(conn)

    def record_repair_outcome(
        self,
        *,
        linked_case_ids: List[str],
        repair_strategy: str,
        repair_summary: str,
        before_solution_hash: str,
        after_solution_hash: str,
        validated: bool,
    ) -> str:
        normalized_case_ids = sorted(str(case_id) for case_id in (linked_case_ids or []) if str(case_id))
        raw_key = json.dumps(
            [
                normalized_case_ids,
                str(repair_strategy or ""),
                str(repair_summary or ""),
                str(before_solution_hash or ""),
                str(after_solution_hash or ""),
                bool(validated),
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        repair_id = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO repair_outcomes (
                    repair_id, linked_case_ids_json, repair_strategy, repair_summary,
                    before_solution_hash, after_solution_hash, validated
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repair_id,
                    json.dumps(normalized_case_ids),
                    str(repair_strategy or ""),
                    str(repair_summary or ""),
                    str(before_solution_hash or ""),
                    str(after_solution_hash or ""),
                    int(bool(validated)),
                ),
            )
        finally:
            self._finish(conn)
        return repair_id

    def list_repair_outcomes(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM repair_outcomes ORDER BY rowid ASC").fetchall()
            return [
                {
                    "repair_id": str(row["repair_id"]),
                    "linked_case_ids": json.loads(row["linked_case_ids_json"] or "[]"),
                    "repair_strategy": str(row["repair_strategy"] or ""),
                    "repair_summary": str(row["repair_summary"] or ""),
                    "before_solution_hash": str(row["before_solution_hash"] or ""),
                    "after_solution_hash": str(row["after_solution_hash"] or ""),
                    "validated": bool(row["validated"]),
                }
                for row in rows
            ]
        finally:
            self._finish(conn)

    def lookup_context(
        self,
        canonical_objective: str,
        tags_level1: List[str],
        tags_level2: List[str],
        lookup_limit: int,
    ) -> Dict[str, Any]:
        tags = {str(tag) for tag in (tags_level1 or []) + (tags_level2 or []) if str(tag)}
        matched_patterns: List[Dict[str, Any]] = []
        exact_counterexamples: List[Dict[str, Any]] = []
        tag_only_counterexamples: List[Dict[str, Any]] = []

        conn = self._connect()
        try:

            for row in conn.execute("SELECT * FROM risk_patterns ORDER BY pattern_id"):
                applicable_tags = json.loads(row["applicable_tags_json"] or "[]")
                applicable_tag_set = {str(tag) for tag in applicable_tags if str(tag)}
                if not tags or not tags.intersection(applicable_tag_set):
                    continue
                matched_patterns.append(
                    {
                        "pattern_id": row["pattern_id"],
                        "title": row["title"],
                        "applicable_tags": applicable_tags,
                        "trigger_features": json.loads(row["trigger_features_json"] or "[]"),
                        "anti_pattern_text": row["anti_pattern_text"],
                        "recommended_checks": json.loads(row["recommended_checks_json"] or "[]"),
                        "evidence_case_ids": json.loads(row["evidence_case_ids_json"] or "[]"),
                    }
                )
                if len(matched_patterns) >= lookup_limit:
                    break

            for row in conn.execute("SELECT * FROM failure_cases ORDER BY rowid DESC"):
                row_tags = set(json.loads(row["tags_level1_json"] or "[]")) | set(json.loads(row["tags_level2_json"] or "[]"))
                objective_match = str(row["canonical_objective"] or "") == str(canonical_objective or "")
                tag_match = bool(tags and row_tags.intersection(tags))
                if not objective_match and not tag_match:
                    continue
                item = {
                    "case_id": row["case_id"],
                    "failure_subtype": row["failure_subtype"],
                    "input_text": row["input_text"],
                    "expected_output": row["expected_output"],
                    "actual_output": row["actual_output"],
                    "failure_type": row["failure_type"],
                    "explanation": row["explanation"],
                }
                if objective_match:
                    exact_counterexamples.append(item)
                else:
                    tag_only_counterexamples.append(item)
        finally:
            self._finish(conn)

        limited_patterns = matched_patterns[:lookup_limit]
        limited_counterexamples = (exact_counterexamples + tag_only_counterexamples)[:lookup_limit]
        return {
            "matched_patterns": limited_patterns,
            "retrieved_counterexamples": limited_counterexamples,
            "anti_patterns": [
                pattern["anti_pattern_text"]
                for pattern in limited_patterns
                if pattern.get("anti_pattern_text")
            ],
            "repair_summaries": [],
            "source_case_ids": [item["case_id"] for item in limited_counterexamples],
        }
