"""Read-only dashboard API for heuristic optimization runs."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.heuristic.reporting import run_report
from src.heuristic.storage import HeuristicStore

router = APIRouter(prefix="/api/heuristic", tags=["heuristic"])


def _data_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    return (
        Path(
            os.environ.get(
                "SOLVITA_HEURISTIC_DATA_DIR", root / ".solvita" / "heuristic"
            )
        )
        .expanduser()
        .resolve()
    )


def _store() -> HeuristicStore:
    return HeuristicStore(_data_dir() / "heuristic.sqlite3")


@router.get("/runs")
def heuristic_runs():
    store = _store()
    try:
        return {"runs": store.runs()}
    finally:
        store.close()


@router.get("/runs/{run_id}")
def heuristic_run(run_id: str):
    store = _store()
    try:
        checkpoint = store.load_checkpoint(run_id)
        if checkpoint is None:
            raise HTTPException(status_code=404, detail="heuristic run not found")
        return {
            "checkpoint": checkpoint,
            "report": run_report(store, run_id),
            "last_events": store.events(run_id)[-20:],
        }
    finally:
        store.close()


@router.get("/runs/{run_id}/trajectory")
def heuristic_trajectory(run_id: str):
    store = _store()
    try:
        transitions = store.transitions(run_id)
        if not transitions and store.load_checkpoint(run_id) is None:
            raise HTTPException(status_code=404, detail="heuristic run not found")
        return {
            "events": store.events(run_id),
            "transitions": transitions,
            "evaluations": store.evaluation_records(
                [transition["child_hash"] for transition in transitions]
            ),
        }
    finally:
        store.close()
