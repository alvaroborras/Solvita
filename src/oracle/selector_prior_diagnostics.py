from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.oracle.selector_prior import (
    CuratedSelectorRow,
    build_curated_training_rows,
    evaluate_selector_prior,
    load_selector_prior_rows,
)


def _tag_set(row: CuratedSelectorRow) -> set[str]:
    tag_text = row.raw_features["canonical_tags_joined"] or row.raw_features["problem_tags_joined"]
    return {tag for tag in str(tag_text).split("|") if tag}


def predict_rule_has_math(row: CuratedSelectorRow) -> str:
    return (
        "oracle.enumeration.n_nested_loops"
        if "math" in _tag_set(row)
        else "oracle.dp.topdown"
    )


def predict_rule_small_math_pattern(row: CuratedSelectorRow) -> str:
    tags = _tag_set(row)
    if tags in ({"math"}, {"math", "brute force"}):
        return "oracle.enumeration.n_nested_loops"
    return "oracle.dp.topdown"


def evaluate_selector_prior_diagnostics(rows: list[CuratedSelectorRow]) -> dict[str, object]:
    model_evaluation = evaluate_selector_prior(rows, eval_protocol="leave_one_problem_out")
    model_predictions = {
        prediction["problem_id"]: prediction for prediction in model_evaluation["predictions"]
    }

    prediction_rows: list[dict[str, Any]] = []
    rule_has_math_correct = 0
    rule_small_math_pattern_correct = 0

    for row in sorted(rows, key=lambda item: item.problem_id):
        model_prediction = model_predictions[row.problem_id]
        rule_has_math_prediction = predict_rule_has_math(row)
        rule_small_math_pattern_prediction = predict_rule_small_math_pattern(row)
        rule_has_math_is_correct = int(rule_has_math_prediction == row.label_family_id)
        rule_small_math_pattern_is_correct = int(
            rule_small_math_pattern_prediction == row.label_family_id
        )
        rule_has_math_correct += rule_has_math_is_correct
        rule_small_math_pattern_correct += rule_small_math_pattern_is_correct

        prediction_rows.append(
            {
                "problem_id": row.problem_id,
                "label_family_id": row.label_family_id,
                "label_cohort": row.label_cohort,
                "canonical_tags_joined": row.raw_features["canonical_tags_joined"],
                "problem_tags_joined": row.raw_features["problem_tags_joined"],
                "description_chars": row.raw_features["description_chars"],
                "public_tests_count": row.raw_features["public_tests_count"],
                "model_prediction": model_prediction["predicted_family_id"],
                "model_correct": model_prediction["model_correct"],
                "model_predicted_dp_probability": model_prediction["predicted_dp_probability"],
                "always_primary_prediction": model_prediction["always_primary_prediction"],
                "always_primary_correct": model_prediction["always_primary_correct"],
                "always_enumeration_prediction": model_prediction["always_enumeration_prediction"],
                "always_enumeration_correct": model_prediction["always_enumeration_correct"],
                "always_dp_prediction": model_prediction["always_dp_prediction"],
                "always_dp_correct": model_prediction["always_dp_correct"],
                "rule_has_math_prediction": rule_has_math_prediction,
                "rule_has_math_correct": rule_has_math_is_correct,
                "rule_small_math_pattern_prediction": rule_small_math_pattern_prediction,
                "rule_small_math_pattern_correct": rule_small_math_pattern_is_correct,
            }
        )

    total = len(rows)
    summary = dict(model_evaluation["summary"])
    summary.update(
        {
            "rule_has_math_accuracy": rule_has_math_correct / total if total else 0.0,
            "rule_small_math_pattern_accuracy": (
                rule_small_math_pattern_correct / total if total else 0.0
            ),
            "rule_has_math_description": (
                "Predict enumeration when tag set contains math; otherwise predict dp."
            ),
            "rule_small_math_pattern_description": (
                "Predict enumeration only for tag sets {math} or {brute force, math}; otherwise predict dp."
            ),
        }
    )
    return {
        "summary": summary,
        "predictions": prediction_rows,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_selector_prior_diagnostics_artifacts(
    *,
    diagnosis: dict[str, object],
    output_dir: Path,
    prefix: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / f"{prefix}_summary.json"
    predictions_path = output_dir / f"{prefix}_predictions.csv"

    summary_path.write_text(
        json.dumps(diagnosis["summary"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    prediction_rows = list(diagnosis["predictions"])
    fieldnames = list(prediction_rows[0].keys()) if prediction_rows else [
        "problem_id",
        "label_family_id",
        "label_cohort",
        "canonical_tags_joined",
        "problem_tags_joined",
        "description_chars",
        "public_tests_count",
        "model_prediction",
        "model_correct",
        "model_predicted_dp_probability",
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


def run_selector_prior_diagnostics_pipeline(
    *,
    input_csv: Path,
    output_dir: Path,
    prefix: str,
) -> dict[str, object]:
    trusted_rows = load_selector_prior_rows(input_csv)
    curated_rows = build_curated_training_rows(trusted_rows)
    diagnosis = evaluate_selector_prior_diagnostics(curated_rows)
    artifacts = write_selector_prior_diagnostics_artifacts(
        diagnosis=diagnosis,
        output_dir=output_dir,
        prefix=prefix,
    )
    return {
        "rows": curated_rows,
        "diagnosis": diagnosis,
        "artifacts": artifacts,
    }
