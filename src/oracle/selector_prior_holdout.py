from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from src.oracle.selector_prior import (
    SelectorPriorModel,
    _sha256_file,
    build_curated_training_rows,
    load_selector_prior_rows,
    predict_selector_prior,
)
from src.oracle.selector_prior_diagnostics import (
    predict_rule_has_math,
    predict_rule_small_math_pattern,
)

DP_FAMILY_ID = "oracle.dp.topdown"
ENUMERATION_FAMILY_ID = "oracle.enumeration.n_nested_loops"


def _problem_id_from_dataset_row(row: dict[str, Any]) -> str:
    problem_id = row.get("id") or row.get("problem_id")
    return str(problem_id or "")


def load_problem_ids_from_trusted_csv(path: Path) -> set[str]:
    problem_ids: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            problem_id = str(row.get("problem_id") or "")
            if problem_id:
                problem_ids.add(problem_id)
    return problem_ids


def load_problem_ids_from_jsonl(path: Path) -> set[str]:
    problem_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            problem_id = _problem_id_from_dataset_row(row)
            if problem_id:
                problem_ids.add(problem_id)
    return problem_ids


def build_holdout_subset(
    *,
    dataset_path: Path,
    output_path: Path,
    excluded_problem_ids: set[str],
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    selected_rows: list[dict[str, Any]] = []
    selected_problem_ids: list[str] = []
    seen_problem_ids: set[str] = set()
    eligible_index = 0

    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            problem_id = _problem_id_from_dataset_row(row)
            if not problem_id or problem_id in excluded_problem_ids or problem_id in seen_problem_ids:
                continue
            seen_problem_ids.add(problem_id)
            if eligible_index < offset:
                eligible_index += 1
                continue
            if len(selected_rows) >= limit:
                break
            selected_rows.append(row)
            selected_problem_ids.append(problem_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in selected_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    overlap_problem_ids = sorted(set(selected_problem_ids) & set(excluded_problem_ids))
    return {
        "dataset_path": str(dataset_path),
        "output_path": str(output_path),
        "offset": offset,
        "limit": limit,
        "num_examples": len(selected_rows),
        "problem_ids": selected_problem_ids,
        "overlap_count": len(overlap_problem_ids),
        "overlap_problem_ids": overlap_problem_ids,
    }


def load_selector_prior_model(model_json_path: Path) -> SelectorPriorModel:
    payload = json.loads(model_json_path.read_text(encoding="utf-8"))
    feature_names = tuple(str(name) for name in payload["feature_names"])
    feature_vocab = {name: index for index, name in enumerate(feature_names)}
    return SelectorPriorModel(
        feature_names=feature_names,
        feature_vocab=feature_vocab,
        weights=np.array(payload["weights"], dtype=np.float64),
        numeric_stats=dict(payload["numeric_stats"]),
        label_mapping={str(key): int(value) for key, value in payload["label_mapping"].items()},
        learning_rate=float(payload.get("learning_rate", 0.1)),
        steps=int(payload.get("steps", 400)),
        l2=float(payload.get("l2", 0.01)),
    )


def _validate_model_provenance(
    *,
    dev_trusted_csv: Path,
    dev_rows: list[Any],
    model_json_path: Path,
) -> None:
    payload = json.loads(model_json_path.read_text(encoding="utf-8"))
    metadata = payload.get("training_metadata") or {}
    expected_problem_ids = sorted({row.problem_id for row in dev_rows})
    mismatches: list[str] = []

    if metadata.get("trusted_csv_path") != str(dev_trusted_csv.resolve()):
        mismatches.append("trusted_csv_path")
    if metadata.get("trusted_csv_sha256") != _sha256_file(dev_trusted_csv):
        mismatches.append("trusted_csv_sha256")
    if metadata.get("problem_ids") != expected_problem_ids:
        mismatches.append("problem_ids")
    if metadata.get("num_examples") != len(dev_rows):
        mismatches.append("num_examples")

    if mismatches:
        raise ValueError(f"model provenance mismatch: {', '.join(mismatches)}")


def _compute_baseline_metrics(
    actual_labels: list[str],
    predicted_labels: list[str],
) -> dict[str, Any]:
    labels = [DP_FAMILY_ID, ENUMERATION_FAMILY_ID]
    for label in [*actual_labels, *predicted_labels]:
        if label not in labels:
            labels.append(label)

    confusion_matrix = {
        actual_label: {predicted_label: 0 for predicted_label in labels}
        for actual_label in labels
    }
    for actual_label, predicted_label in zip(actual_labels, predicted_labels):
        confusion_matrix[actual_label][predicted_label] += 1

    total = len(actual_labels)
    actual_dp_total = sum(1 for label in actual_labels if label == DP_FAMILY_ID)
    actual_enumeration_total = sum(1 for label in actual_labels if label == ENUMERATION_FAMILY_ID)
    correct = sum(
        1 for actual_label, predicted_label in zip(actual_labels, predicted_labels) if actual_label == predicted_label
    )
    return {
        "accuracy": correct / total if total else 0.0,
        "dp_recall": (
            confusion_matrix[DP_FAMILY_ID][DP_FAMILY_ID] / actual_dp_total if actual_dp_total else 0.0
        ),
        "enumeration_recall": (
            confusion_matrix[ENUMERATION_FAMILY_ID][ENUMERATION_FAMILY_ID] / actual_enumeration_total
            if actual_enumeration_total
            else 0.0
        ),
        "confusion_matrix": confusion_matrix,
        "balanced_accuracy": (
            (
                confusion_matrix[DP_FAMILY_ID][DP_FAMILY_ID] / actual_dp_total
                if actual_dp_total
                else 0.0
            )
            + (
                confusion_matrix[ENUMERATION_FAMILY_ID][ENUMERATION_FAMILY_ID] / actual_enumeration_total
                if actual_enumeration_total
                else 0.0
            )
        )
        / 2.0,
    }


def evaluate_selector_prior_external_holdout(
    *,
    dev_trusted_csv: Path,
    holdout_trusted_csv: Path,
    dev_model_json: Path,
) -> dict[str, Any]:
    dev_rows = build_curated_training_rows(load_selector_prior_rows(dev_trusted_csv))
    holdout_rows = build_curated_training_rows(load_selector_prior_rows(holdout_trusted_csv))

    dev_problem_ids = sorted({row.problem_id for row in dev_rows})
    holdout_problem_ids = sorted({row.problem_id for row in holdout_rows})
    overlap_problem_ids = sorted(set(dev_problem_ids) & set(holdout_problem_ids))
    if overlap_problem_ids:
        raise ValueError(f"dev/holdout overlap detected: {', '.join(overlap_problem_ids)}")

    _validate_model_provenance(
        dev_trusted_csv=dev_trusted_csv,
        dev_rows=dev_rows,
        model_json_path=dev_model_json,
    )

    model = load_selector_prior_model(dev_model_json)
    logistic_predictions = {
        prediction.problem_id: prediction
        for prediction in predict_selector_prior(model, holdout_rows)
    }

    prediction_rows: list[dict[str, Any]] = []
    logistic_correct = 0
    always_primary_correct = 0
    always_enumeration_correct = 0
    always_dp_correct = 0
    rule_has_math_correct = 0
    rule_small_math_pattern_correct = 0
    actual_labels: list[str] = []
    baseline_predicted_labels = {
        "logistic": [],
        "always_primary": [],
        "always_enumeration": [],
        "always_dp": [],
        "rule_has_math": [],
        "rule_small_math_pattern": [],
    }

    for row in sorted(holdout_rows, key=lambda item: item.problem_id):
        logistic_prediction = logistic_predictions[row.problem_id]
        rule_has_math_prediction = predict_rule_has_math(row)
        rule_small_math_pattern_prediction = predict_rule_small_math_pattern(row)
        rule_has_math_is_correct = int(rule_has_math_prediction == row.label_family_id)
        rule_small_math_pattern_is_correct = int(
            rule_small_math_pattern_prediction == row.label_family_id
        )

        logistic_correct += logistic_prediction.model_correct
        always_primary_correct += logistic_prediction.always_primary_correct
        always_enumeration_correct += logistic_prediction.always_enumeration_correct
        always_dp_correct += logistic_prediction.always_dp_correct
        rule_has_math_correct += rule_has_math_is_correct
        rule_small_math_pattern_correct += rule_small_math_pattern_is_correct
        actual_labels.append(row.label_family_id)
        baseline_predicted_labels["logistic"].append(logistic_prediction.predicted_family_id)
        baseline_predicted_labels["always_primary"].append(logistic_prediction.always_primary_prediction)
        baseline_predicted_labels["always_enumeration"].append(
            logistic_prediction.always_enumeration_prediction
        )
        baseline_predicted_labels["always_dp"].append(logistic_prediction.always_dp_prediction)
        baseline_predicted_labels["rule_has_math"].append(rule_has_math_prediction)
        baseline_predicted_labels["rule_small_math_pattern"].append(rule_small_math_pattern_prediction)

        prediction_rows.append(
            {
                "problem_id": row.problem_id,
                "label_family_id": row.label_family_id,
                "label_cohort": row.label_cohort,
                "canonical_tags_joined": row.raw_features["canonical_tags_joined"],
                "problem_tags_joined": row.raw_features["problem_tags_joined"],
                "logistic_prediction": logistic_prediction.predicted_family_id,
                "logistic_correct": logistic_prediction.model_correct,
                "logistic_predicted_dp_probability": logistic_prediction.predicted_dp_probability,
                "always_primary_prediction": logistic_prediction.always_primary_prediction,
                "always_primary_correct": logistic_prediction.always_primary_correct,
                "always_enumeration_prediction": logistic_prediction.always_enumeration_prediction,
                "always_enumeration_correct": logistic_prediction.always_enumeration_correct,
                "always_dp_prediction": logistic_prediction.always_dp_prediction,
                "always_dp_correct": logistic_prediction.always_dp_correct,
                "rule_has_math_prediction": rule_has_math_prediction,
                "rule_has_math_correct": rule_has_math_is_correct,
                "rule_small_math_pattern_prediction": rule_small_math_pattern_prediction,
                "rule_small_math_pattern_correct": rule_small_math_pattern_is_correct,
            }
        )

    total = len(holdout_rows)
    baseline_metrics = {
        baseline_name: _compute_baseline_metrics(actual_labels, predicted_labels)
        for baseline_name, predicted_labels in baseline_predicted_labels.items()
    }
    summary = {
        "evaluation_kind": "external_holdout_dev_to_external_holdout",
        "dev_num_examples": len(dev_rows),
        "dev_num_unique_problem_ids": len(dev_problem_ids),
        "num_examples": len(holdout_rows),
        "num_unique_problem_ids": len(holdout_problem_ids),
        "label_distribution": dict(Counter(row.label_family_id for row in holdout_rows)),
        "cohort_distribution": dict(Counter(row.label_cohort for row in holdout_rows)),
        "dev_holdout_overlap_count": len(overlap_problem_ids),
        "dev_holdout_overlap_problem_ids": overlap_problem_ids,
        "always_primary_accuracy": always_primary_correct / total if total else 0.0,
        "always_enumeration_accuracy": always_enumeration_correct / total if total else 0.0,
        "always_dp_accuracy": always_dp_correct / total if total else 0.0,
        "logistic_holdout_accuracy": logistic_correct / total if total else 0.0,
        "rule_has_math_accuracy": rule_has_math_correct / total if total else 0.0,
        "rule_small_math_pattern_accuracy": (
            rule_small_math_pattern_correct / total if total else 0.0
        ),
        "baseline_metrics": baseline_metrics,
    }
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


def write_selector_prior_holdout_artifacts(
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


def run_selector_prior_external_holdout_pipeline(
    *,
    dev_trusted_csv: Path,
    holdout_trusted_csv: Path,
    dev_model_json: Path,
    output_dir: Path,
    prefix: str,
) -> dict[str, Any]:
    evaluation = evaluate_selector_prior_external_holdout(
        dev_trusted_csv=dev_trusted_csv,
        holdout_trusted_csv=holdout_trusted_csv,
        dev_model_json=dev_model_json,
    )
    artifacts = write_selector_prior_holdout_artifacts(
        evaluation=evaluation,
        output_dir=output_dir,
        prefix=prefix,
    )
    return {
        "evaluation": evaluation,
        "artifacts": artifacts,
    }
