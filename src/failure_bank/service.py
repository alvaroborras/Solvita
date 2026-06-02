from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


class FailureBankService:
    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)
        self.db_path = self.root / "failure_bank.db"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
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

    def record_failure_case(self, payload: Dict[str, Any]) -> str:
        canonical_objective = str(payload.get("canonical_objective", "") or "")
        input_text = str(payload.get("input_text", "") or "")
        actual_output = str(payload.get("actual_output", "") or "")
        raw_key = f"{canonical_objective}\n{input_text}\n{actual_output}"
        case_id = str(payload.get("case_id") or hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20])
        with sqlite3.connect(self.db_path) as conn:
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
                    str(payload.get("expected_output", "") or ""),
                    actual_output,
                    str(payload.get("checker_context", "") or ""),
                    str(payload.get("trusted_level", "high") or "high"),
                    str(payload.get("source_run_id", "") or ""),
                    str(payload.get("source_solution_hash", "") or ""),
                    str(payload.get("explanation", "") or ""),
                    int(bool(payload.get("minimized", False))),
                ),
            )
        return case_id

    def record_risk_pattern(self, payload: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
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

    def lookup_context(
        self,
        canonical_objective: str,
        tags_level1: List[str],
        tags_level2: List[str],
        lookup_limit: int,
    ) -> Dict[str, Any]:
        tags = {str(tag) for tag in (tags_level1 or []) + (tags_level2 or []) if str(tag)}
        matched_patterns: List[Dict[str, Any]] = []
        counterexamples: List[Dict[str, Any]] = []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

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
                counterexamples.append(
                    {
                        "case_id": row["case_id"],
                        "failure_subtype": row["failure_subtype"],
                        "input_text": row["input_text"],
                        "expected_output": row["expected_output"],
                        "actual_output": row["actual_output"],
                        "failure_type": row["failure_type"],
                        "explanation": row["explanation"],
                    }
                )
                if len(counterexamples) >= lookup_limit:
                    break

        limited_patterns = matched_patterns[:lookup_limit]
        limited_counterexamples = counterexamples[:lookup_limit]
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
