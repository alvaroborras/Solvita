from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.oracle.selector_prior_holdout import _compute_baseline_metrics


def _load_predictions_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_holdout_prediction_rows(
    rows: list[dict[str, str]],
    *,
    evaluation_kind: str = "cumulative_external_holdout",
) -> dict[str, Any]:
    required_fields = (
        "problem_id",
        "label_family_id",
        "logistic_prediction",
        "always_primary_prediction",
        "always_enumeration_prediction",
        "always_dp_prediction",
        "rule_has_math_prediction",
        "rule_small_math_pattern_prediction",
    )
    seen_problem_ids: set[str] = set()
    for row in rows:
        missing_fields = [field for field in required_fields if field not in row]
        if missing_fields:
            raise ValueError(f"missing required prediction columns: {', '.join(missing_fields)}")
        problem_id = str(row.get("problem_id") or "")
        if not problem_id:
            raise ValueError("missing problem_id in holdout predictions row")
        if problem_id in seen_problem_ids:
            raise ValueError(f"duplicate problem_id in cumulative holdout predictions: {problem_id}")
        seen_problem_ids.add(problem_id)

    sorted_rows = sorted(rows, key=lambda row: str(row["problem_id"]))
    actual_labels = [str(row["label_family_id"]) for row in sorted_rows]
    baseline_prediction_columns = {
        "logistic": "logistic_prediction",
        "always_primary": "always_primary_prediction",
        "always_enumeration": "always_enumeration_prediction",
        "always_dp": "always_dp_prediction",
        "rule_has_math": "rule_has_math_prediction",
        "rule_small_math_pattern": "rule_small_math_pattern_prediction",
    }
    baseline_metrics = {
        baseline_name: _compute_baseline_metrics(
            actual_labels,
            [str(row[prediction_column]) for row in sorted_rows],
        )
        for baseline_name, prediction_column in baseline_prediction_columns.items()
    }

    summary = {
        "evaluation_kind": evaluation_kind,
        "num_examples": len(sorted_rows),
        "num_unique_problem_ids": len(seen_problem_ids),
        "label_distribution": dict(Counter(actual_labels)),
        "always_primary_accuracy": baseline_metrics["always_primary"]["accuracy"],
        "always_enumeration_accuracy": baseline_metrics["always_enumeration"]["accuracy"],
        "always_dp_accuracy": baseline_metrics["always_dp"]["accuracy"],
        "logistic_accuracy": baseline_metrics["logistic"]["accuracy"],
        "rule_has_math_accuracy": baseline_metrics["rule_has_math"]["accuracy"],
        "rule_small_math_pattern_accuracy": baseline_metrics["rule_small_math_pattern"]["accuracy"],
        "baseline_metrics": baseline_metrics,
    }
    return {
        "summary": summary,
        "predictions": sorted_rows,
    }


def summarize_holdout_predictions(
    predictions_csv_paths: list[Path],
    *,
    evaluation_kind: str = "cumulative_external_holdout",
) -> dict[str, Any]:
    merged_rows: list[dict[str, str]] = []
    seen_problem_ids: set[str] = set()
    for predictions_csv_path in predictions_csv_paths:
        rows = _load_predictions_csv(predictions_csv_path)
        for row in rows:
            problem_id = str(row.get("problem_id") or "")
            if problem_id in seen_problem_ids:
                raise ValueError(f"duplicate problem_id in cumulative holdout predictions: {problem_id}")
            seen_problem_ids.add(problem_id)
            merged_rows.append(row)
    return summarize_holdout_prediction_rows(merged_rows, evaluation_kind=evaluation_kind)


def write_selector_prior_holdout_cumulative_artifacts(
    *,
    evaluation: dict[str, Any],
    output_dir: Path,
    prefix: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"{prefix}_summary.json"
    predictions_path = output_dir / f"{prefix}_predictions.csv"

    summary_path.write_text(
        json.dumps(evaluation["summary"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    prediction_rows = list(evaluation["predictions"])
    fieldnames = list(prediction_rows[0].keys()) if prediction_rows else [
        "problem_id",
        "label_family_id",
        "label_cohort",
        "canonical_tags_joined",
        "problem_tags_joined",
        "logistic_prediction",
        "logistic_correct",
        "logistic_predicted_dp_probability",
        "always_primary_prediction",
        "always_primary_correct",
        "always_enumeration_prediction",
        "always_enumeration_correct",
        "always_dp_prediction",
        "always_dp_correct",
        "rule_has_math_prediction",
        "rule_has_math_correct",
        "rule_small_math_pattern_prediction",
        "rule_small_math_pattern_correct",
    ]
    _write_csv(predictions_path, prediction_rows, fieldnames=fieldnames)
    return {
        "summary_json": summary_path,
        "predictions_csv": predictions_path,
    }


def _derive_evaluation_kind(prefix: str) -> str:
    stem = "selector_prior_holdout_cumulative"
    if not prefix.startswith(stem):
        return "cumulative_external_holdout"
    suffix = prefix[len(stem):].strip("_")
    if not suffix:
        return "cumulative_external_holdout"
    return f"cumulative_external_holdout_{suffix}"


def run_selector_prior_holdout_cumulative_pipeline(
    *,
    predictions_csv_paths: list[Path],
    output_dir: Path,
    prefix: str,
) -> dict[str, Any]:
    evaluation = summarize_holdout_predictions(
        predictions_csv_paths,
        evaluation_kind=_derive_evaluation_kind(prefix),
    )
    artifacts = write_selector_prior_holdout_cumulative_artifacts(
        evaluation=evaluation,
        output_dir=output_dir,
        prefix=prefix,
    )
    return {
        "evaluation": evaluation,
        "artifacts": artifacts,
    }
