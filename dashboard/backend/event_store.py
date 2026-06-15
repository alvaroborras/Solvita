from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .config import DATA_DIR
except ImportError:
    from config import DATA_DIR


class EventStore:
    """Persists run events to JSON files for replay."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def save_run(
        self,
        run_id: str,
        problem_id: str,
        problem: dict[str, Any],
        config: dict[str, Any],
        events: list[dict[str, Any]],
        started_at: str,
        final_status: str | None = None,
        completed_at: str | None = None,
    ) -> Path:
        completed_at = completed_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        run_data = {
            "run_id": run_id,
            "problem_id": problem_id,
            "problem": problem,
            "config": config,
            "started_at": started_at,
            "completed_at": completed_at,
            "final_status": final_status,
            "events": events,
        }
        path = DATA_DIR / f"{run_id}.json"
        with self._lock:
            path.write_text(json.dumps(run_data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._update_index(run_id, problem_id, problem, final_status, started_at, completed_at, events)
        return path

    def list_runs(self) -> list[dict[str, Any]]:
        index_path = DATA_DIR / "index.json"
        with self._lock:
            if not index_path.exists():
                return []
            return json.loads(index_path.read_text(encoding="utf-8"))

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        path = DATA_DIR / f"{run_id}.json"
        with self._lock:
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def delete_run(self, run_id: str) -> bool:
        path = DATA_DIR / f"{run_id}.json"
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            index_path = DATA_DIR / "index.json"
            if index_path.exists():
                runs = json.loads(index_path.read_text(encoding="utf-8"))
                runs = [r for r in runs if r["run_id"] != run_id]
                index_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
            return True

    def _update_index(
        self,
        run_id: str,
        problem_id: str,
        problem: dict[str, Any],
        final_status: str | None,
        started_at: str,
        completed_at: str,
        events: list[dict[str, Any]],
    ) -> None:
        index_path = DATA_DIR / "index.json"
        runs: list[dict[str, Any]] = []
        if index_path.exists():
            runs = json.loads(index_path.read_text(encoding="utf-8"))

        final_event = None
        for e in reversed(events):
            ev = e.get("event", e)
            if ev.get("type") == "final":
                final_event = ev
                break

        meta = (problem or {}).get("_metadata", {}) if isinstance(problem, dict) else {}
        problem_name = str(meta.get("name") or meta.get("question_id") or problem_id)
        problem_family = str(meta.get("family") or "")
        summary = {
            "run_id": run_id,
            "problem_id": problem_id,
            "problem_name": problem_name,
            "problem_family": problem_family,
            "status": "completed",
            "final_status": final_status or (final_event.get("status") if final_event else None),
            "started_at": started_at,
            "completed_at": completed_at,
            "iterations": final_event.get("iterations") if final_event else None,
            "pass_rate": final_event.get("pass_rate") if final_event else None,
        }
        runs = [r for r in runs if r["run_id"] != run_id]
        runs.insert(0, summary)
        index_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
