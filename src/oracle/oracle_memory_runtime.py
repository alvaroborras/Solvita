from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.oracle.oracle_memory_db import OracleMemoryDB
from src.oracle.oracle_memory_policy import recipe_bucket_from_template_name


def _resolve_memory_mode(config: dict[str, Any] | None) -> str:
    if not isinstance(config, dict):
        return "off"
    trainable_memory = config.get("trainable_memory", {}) or {}
    return str(trainable_memory.get("oracle_memory_mode", "off") or "off").strip() or "off"


def _resolve_snapshot_id(
    config: dict[str, Any] | None,
    db: OracleMemoryDB,
) -> str | None:
    trainable_memory = (config or {}).get("trainable_memory", {}) or {}
    configured_snapshot_id = str(trainable_memory.get("oracle_memory_snapshot_id") or "").strip()
    if not db.db_path.exists():
        return None
    if not configured_snapshot_id:
        return None
    return configured_snapshot_id


def _snapshot_exists(db: OracleMemoryDB, snapshot_id: str) -> bool:
    if not db.db_path.exists():
        return False
    try:
        with sqlite3.connect(db.db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }
            if "oracle_model_snapshots" in tables:
                row = conn.execute(
                    """
                    SELECT 1
                    FROM oracle_model_snapshots
                    WHERE snapshot_id = ?
                    LIMIT 1
                    """,
                    (snapshot_id,),
                ).fetchone()
                if row is not None:
                    return True
            if "oracle_action_stats" in tables:
                row = conn.execute(
                    """
                    SELECT 1
                    FROM oracle_action_stats
                    WHERE snapshot_id = ?
                    LIMIT 1
                    """,
                    (snapshot_id,),
                ).fetchone()
                if row is not None:
                    return True
    except sqlite3.Error:
        return False
    return False


def _is_low_confidence_action(stats: dict[str, Any]) -> bool:
    support_count = int(stats.get("support_count", 0) or 0)
    observed_success_rate = float(stats.get("observed_success_rate", 0.0) or 0.0)
    mean_predicted_success_probability = float(stats.get("mean_predicted_success_probability", 0.0) or 0.0)
    if support_count <= 0:
        return False
    if observed_success_rate < 0.5:
        return True
    return mean_predicted_success_probability > 0.0 and mean_predicted_success_probability < 0.5


def decide_oracle_memory_gate(
    *,
    config: dict[str, Any] | None,
    selected_template_name: str,
    db: OracleMemoryDB | None = None,
) -> dict[str, Any]:
    normalized_template_name = str(selected_template_name or "").strip()
    selected_action = recipe_bucket_from_template_name(normalized_template_name) if normalized_template_name else None
    mode = _resolve_memory_mode(config)
    decision = {
        "applied": False,
        "reason": "memory_mode_off" if mode == "off" else "no_runtime_signal",
        "selected_action": selected_action,
        "replacement_action": None,
        "candidate_action_set": [selected_action] if selected_action else [],
        "exploration_flag": False,
        "memory_mode": mode,
        "snapshot_id": None,
        "stats": None,
    }
    if mode == "off":
        return decision
    if not normalized_template_name:
        decision["reason"] = "template_unknown"
        return decision

    if db is None:
        trainable_memory = (config or {}).get("trainable_memory", {}) or {}
        data_dir = Path(trainable_memory.get("data_dir", "data/memory"))
        db = OracleMemoryDB.from_data_dir(data_dir)

    snapshot_id = _resolve_snapshot_id(config, db)
    if not snapshot_id or not _snapshot_exists(db, snapshot_id):
        decision["reason"] = "no_snapshot_available"
        return decision

    decision["snapshot_id"] = snapshot_id
    stats_row = next(
        (
            row
            for row in db.list_action_stats(snapshot_id)
            if str(row.get("action_id") or "").strip() == selected_action
        ),
        None,
    )
    if stats_row is None:
        decision["reason"] = "no_selected_action_stats"
        return decision

    stats = dict(stats_row.get("stats") or {})
    decision["stats"] = stats
    if _is_low_confidence_action(stats):
        decision["applied"] = True
        decision["reason"] = "low_confidence_selected_action"
        return decision

    decision["reason"] = "selected_action_supported"
    return decision
