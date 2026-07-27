"""Read-only run and comparison metrics."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from typing import Any, Iterable

from .storage import HeuristicStore


def _summary(values: Iterable[float]) -> dict[str, float | int] | None:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return None
    ordered = sorted(finite)
    tail = ordered[: max(1, math.ceil(0.2 * len(ordered)))]
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": mean(ordered),
        "max": ordered[-1],
        "bottom_20pct_mean": mean(tail),
    }


def _elapsed_seconds(events: list[dict[str, Any]]) -> float | None:
    if len(events) < 2:
        return 0.0 if events else None
    timestamps = [
        datetime.fromisoformat(str(event["created_at"]).replace("Z", "+00:00"))
        for event in events
    ]
    return max(0.0, (max(timestamps) - min(timestamps)).total_seconds())


def _best_candidate(
    checkpoint: dict[str, Any], events: list[dict[str, Any]]
) -> str | None:
    validation_incumbent = (checkpoint.get("metadata") or {}).get(
        "validation_incumbent_hash"
    )
    if validation_incumbent:
        return str(validation_incumbent)
    entries = (checkpoint.get("archive") or {}).get("entries") or []
    if entries:
        return str(
            max(
                entries,
                key=lambda item: (
                    float(item.get("quality", float("-inf"))),
                    str(item.get("candidate_hash", "")),
                ),
            )["candidate_hash"]
        )
    for event in reversed(events):
        candidate_hash = event["payload"].get("best_candidate_hash")
        if candidate_hash:
            return str(candidate_hash)
    return None


def _bks_improvements(rows: list[dict[str, Any]], minimize: bool) -> dict[str, int]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["fidelity"]), str(row["instance_id"]))].append(
            float(row["objective"])
        )
    counts: Counter[str] = Counter()
    for (fidelity, _), values in grouped.items():
        best = values[0]
        for value in values[1:]:
            improved = value < best if minimize else value > best
            if improved:
                counts[fidelity] += 1
                best = value
    return dict(counts)


def run_report(store: HeuristicStore, run_id: str) -> dict[str, Any]:
    run = store.run(run_id) or {}
    transitions = store.transitions(run_id)
    checkpoint = store.load_checkpoint(run_id) or {}
    events = store.events(run_id)
    hashes = [row["child_hash"] for row in transitions]
    if not hashes:
        hashes = [
            str(candidate_hash)
            for event in events
            for candidate_hash in (
                list(event["payload"].get("promoted") or [])
                + (
                    [event["payload"]["best_candidate_hash"]]
                    if event["payload"].get("best_candidate_hash")
                    else []
                )
            )
        ]
    records = store.evaluation_records(hashes)
    failures = Counter(record.get("failure") or "ok" for record in records)
    curve: list[float] = []
    best = float("-inf")
    for row in transitions:
        best = max(best, float(row["payload"].get("quality", float("-inf"))))
        curve.append(best)
    if not curve:
        for event in events:
            if event["kind"] != "oa_result":
                continue
            raw_curve = event["payload"].get("best_so_far") or []
            curve = [float(value) for value in raw_curve]
            if not curve and event["payload"].get("best_score") is not None:
                curve = [float(event["payload"]["best_score"])]
    finite_curve = [value for value in curve if math.isfinite(value)]
    auc = mean(finite_curve) if finite_curve else None

    best_hash = _best_candidate(checkpoint, events)
    best_records = (
        store.evaluation_records([best_hash]) if best_hash is not None else []
    )
    train_ids: set[str] = set()
    validation_ids: set[str] = set()
    minimize = True
    try:
        from .plugins import load_problem

        problem = load_problem(str(run["problem_id"]))
        train, validation = problem.adapter.split()
        train_ids, validation_ids = set(train), set(validation)
        minimize = problem.manifest.objective == "minimize"
    except (KeyError, FileNotFoundError, ImportError, ValueError):
        pass
    raw_objectives: dict[str, Any] = {}
    for fidelity in ("10s", "60s"):
        fidelity_rows = [
            record
            for record in best_records
            if record["fidelity"] == fidelity
            and record.get("feasible")
            and record.get("objective") is not None
        ]
        raw_objectives[fidelity] = {
            "training": _summary(
                record["objective"]
                for record in fidelity_rows
                if not train_ids or record["instance_id"] in train_ids
            ),
            "validation": _summary(
                record["objective"]
                for record in fidelity_rows
                if record["instance_id"] in validation_ids
            ),
        }

    entries = (checkpoint.get("archive") or {}).get("entries") or []
    best_entry = next(
        (entry for entry in entries if entry.get("candidate_hash") == best_hash), None
    )
    instance_scores = list((best_entry or {}).get("instance_scores", {}).values())
    tail_summary = _summary(instance_scores)
    metadata = checkpoint.get("metadata") or {}
    oa_wall_time = next(
        (
            event["payload"].get("metadata", {}).get("wall_time")
            for event in reversed(events)
            if event["kind"] == "oa_result"
            and event["payload"].get("metadata", {}).get("wall_time") is not None
        ),
        None,
    )
    return {
        "run_id": run_id,
        "engine": run.get("engine"),
        "proposals": int(checkpoint.get("proposals", len(transitions))),
        "evaluation_records": len(records),
        "best_candidate_hash": best_hash,
        "best_so_far": curve,
        "area_under_best_so_far": auc,
        "best_training": checkpoint.get("best_training"),
        "best_validation_lcb": checkpoint.get("best_validation_lcb"),
        "bottom_tail_quality": (
            tail_summary["bottom_20pct_mean"] if tail_summary is not None else None
        ),
        "raw_objectives": raw_objectives,
        "support_calls": checkpoint.get("support_calls", 0),
        "evaluation_calls": checkpoint.get("evaluation_calls", len(records)),
        "failure_counts": dict(failures),
        "invalid_or_tle_rate": (
            sum(count for failure, count in failures.items() if failure != "ok")
            / len(records)
            if records
            else 0.0
        ),
        "qd_coverage": len(entries),
        "bks_improvements": _bks_improvements(
            store.bks_snapshot_records(run.get("problem_id"), run_id),
            minimize=minimize,
        ),
        "tokens": metadata.get("tokens"),
        "cost": metadata.get("cost"),
        "wall_time_seconds": (
            float(oa_wall_time)
            if oa_wall_time is not None
            else _elapsed_seconds(events)
        ),
    }


def comparison_report(store: HeuristicStore, run_ids: list[str]) -> dict[str, Any]:
    reports = [run_report(store, run_id) for run_id in run_ids]
    by_engine: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        by_engine[str(report.get("engine") or "unknown")].append(report)

    def aggregate(group: list[dict[str, Any]]) -> dict[str, Any]:
        keys = (
            "area_under_best_so_far",
            "best_training",
            "best_validation_lcb",
            "bottom_tail_quality",
            "invalid_or_tle_rate",
            "qd_coverage",
            "evaluation_calls",
            "support_calls",
            "tokens",
            "cost",
            "wall_time_seconds",
        )
        result: dict[str, Any] = {"replicates": len(group)}
        for key in keys:
            values = [
                float(report[key]) for report in group if report.get(key) is not None
            ]
            result[f"mean_{key}"] = mean(values) if values else None
        return result

    return {
        "runs": reports,
        "by_engine": {
            engine: aggregate(group) for engine, group in sorted(by_engine.items())
        },
    }
