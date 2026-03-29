from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


SUPPORTED_FAMILY_IDS = (
    "oracle.enumeration.n_nested_loops",
    "oracle.dp.topdown",
)

DEFAULT_COHORT_PRIORITY = (
    "selected_family",
    "rerun",
    "unknown",
)

ALLOWED_FEATURE_COLUMNS = (
    "candidate_family_pool",
    "candidate_family_pool_joined",
    "primary_family_id",
    "fallback_family_id",
    "problem_tags_joined",
    "canonical_tags_joined",
    "problem_type_joined",
    "key_elements_joined",
    "objective_text",
    "graph_type",
    "is_multi_solution",
    "data_structures_joined",
    "constraints_json",
    "description_chars",
    "public_tests_count",
)

LEAKY_FEATURE_COLUMNS = (
    "decision",
    "artifact_kind",
    "compile_success",
    "public_self_check_pass",
    "probe_pack_pass",
    "certified_count",
    "certified_target_count",
    "cert_ratio",
    "reward",
    "reward_reason",
    "failure_stage",
    "failure_subtype",
    "checker_fallback_used",
    "solver_attempt_count",
    "selected_template_name",
    "compact_retry_count",
    "cost_llm_calls",
    "prompt_char_stats",
    "prompt_chars_generator",
    "prompt_chars_validator",
    "prompt_chars_checker",
    "prompt_chars_solver",
    "source_path",
    "problem_source_path",
    "selected_family_id",
    "is_trusted_label",
    "sample_weight",
)

LABEL_TO_TARGET = {
    "oracle.enumeration.n_nested_loops": 0,
    "oracle.dp.topdown": 1,
}

TARGET_TO_LABEL = {target: label for label, target in LABEL_TO_TARGET.items()}

NUMERIC_FEATURE_NAMES = {
    "description_chars": "numeric::description_chars_log1p",
    "public_tests_count": "numeric::public_tests_count_log1p",
}


@dataclass(frozen=True)
class CuratedSelectorRow:
    problem_id: str
    label_family_id: str
    label_cohort: str
    primary_family_id: str
    fallback_family_id: str
    candidate_family_pool: tuple[str, ...]
    raw_features: dict[str, Any]
    source_path: str


@dataclass(frozen=True)
class FeatureFrame:
    matrix: np.ndarray
    labels: np.ndarray
    feature_names: tuple[str, ...]
    feature_vocab: dict[str, int]
    numeric_stats: dict[str, dict[str, float]]


@dataclass(frozen=True)
class SelectorPriorModel:
    feature_names: tuple[str, ...]
    feature_vocab: dict[str, int]
    weights: np.ndarray
    numeric_stats: dict[str, dict[str, float]]
    label_mapping: dict[str, int]
    learning_rate: float
    steps: int
    l2: float


@dataclass(frozen=True)
class PredictionRow:
    problem_id: str
    label_family_id: str
    predicted_family_id: str
    predicted_dp_probability: float
    primary_family_id: str
    fallback_family_id: str
    label_cohort: str
    model_correct: int
    always_primary_prediction: str
    always_primary_correct: int
    always_enumeration_prediction: str
    always_enumeration_correct: int
    always_dp_prediction: str
    always_dp_correct: int


def _coerce_int(value: Any) -> int:
    if value in ("", None):
        return 0
    if isinstance(value, bool):
        return int(value)
    return int(value)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _split_joined(value: Any) -> list[str]:
    if value in ("", None):
        return []
    return [item.strip() for item in str(value).split("|") if item and item.strip()]


def _parse_candidate_family_pool(value: Any, candidate_family_pool_joined: str = "") -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item))
    if value not in ("", None):
        text = str(value).strip()
        if text.startswith("["):
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError(f"candidate_family_pool must decode to list: {text}")
            return tuple(str(item) for item in parsed if str(item))
        return tuple(_split_joined(text))
    if candidate_family_pool_joined:
        return tuple(_split_joined(candidate_family_pool_joined))
    return ()


def _cohort_rank_map(cohort_priority: tuple[str, ...]) -> dict[str, int]:
    return {name: index for index, name in enumerate(cohort_priority)}


def _normalize_allowed_features(
    row: dict[str, Any],
    candidate_family_pool: tuple[str, ...],
    primary_family_id: str,
    fallback_family_id: str,
) -> dict[str, Any]:
    candidate_family_pool_joined = "|".join(candidate_family_pool)
    return {
        "candidate_family_pool": candidate_family_pool,
        "candidate_family_pool_joined": candidate_family_pool_joined,
        "primary_family_id": primary_family_id,
        "fallback_family_id": fallback_family_id,
        "problem_tags_joined": str(row.get("problem_tags_joined") or ""),
        "canonical_tags_joined": str(row.get("canonical_tags_joined") or ""),
        "problem_type_joined": str(row.get("problem_type_joined") or ""),
        "key_elements_joined": str(row.get("key_elements_joined") or ""),
        "objective_text": str(row.get("objective_text") or ""),
        "graph_type": str(row.get("graph_type") or ""),
        "is_multi_solution": _coerce_bool(row.get("is_multi_solution")),
        "data_structures_joined": str(row.get("data_structures_joined") or ""),
        "constraints_json": str(row.get("constraints_json") or ""),
        "description_chars": _coerce_int(row.get("description_chars")),
        "public_tests_count": _coerce_int(row.get("public_tests_count")),
    }


def _validate_candidate_family_pool(
    *,
    problem_id: str,
    candidate_family_pool: tuple[str, ...],
    label_family_id: str,
) -> None:
    if not candidate_family_pool:
        raise ValueError(f"candidate_family_pool must not be empty for problem_id={problem_id}")
    if len(candidate_family_pool) != 2:
        raise ValueError(f"candidate_family_pool must contain exactly two families for problem_id={problem_id}")

    unsupported_family_ids = [
        family_id for family_id in candidate_family_pool if family_id not in SUPPORTED_FAMILY_IDS
    ]
    if unsupported_family_ids:
        raise ValueError(
            "unsupported family in candidate_family_pool "
            f"for problem_id={problem_id}: {', '.join(unsupported_family_ids)}"
        )
    if label_family_id not in candidate_family_pool:
        raise ValueError(f"selected_family_id must be in candidate_family_pool for problem_id={problem_id}")
    if len(set(candidate_family_pool)) != 2:
        raise ValueError(
            f"candidate_family_pool must contain two distinct families for problem_id={problem_id}"
        )


def _allowlisted_feature_signature(row: CuratedSelectorRow) -> tuple[tuple[str, Any], ...]:
    return tuple((feature_name, row.raw_features[feature_name]) for feature_name in ALLOWED_FEATURE_COLUMNS)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_selector_prior_rows(input_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with input_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            if str(raw_row.get("is_trusted_label", "")).strip() != "1":
                continue
            label_family_id = str(raw_row.get("selected_family_id") or "")
            if label_family_id not in SUPPORTED_FAMILY_IDS:
                raise ValueError(f"unsupported selected_family_id: {label_family_id}")
            rows.append(dict(raw_row))
    return rows


def derive_label_cohort(source_path: str) -> str:
    if "selected_family" in source_path:
        return "selected_family"
    if "rerun" in source_path:
        return "rerun"
    return "unknown"


def build_curated_training_rows(
    rows: list[dict[str, Any]],
    cohort_priority: tuple[str, ...] = DEFAULT_COHORT_PRIORITY,
) -> list[CuratedSelectorRow]:
    by_problem_id: dict[str, list[CuratedSelectorRow]] = defaultdict(list)

    for raw_row in rows:
        problem_id = str(raw_row.get("problem_id") or "")
        if not problem_id:
            raise ValueError("missing problem_id in selector prior row")

        label_family_id = str(raw_row.get("selected_family_id") or "")
        if label_family_id not in SUPPORTED_FAMILY_IDS:
            raise ValueError(f"unsupported selected_family_id for {problem_id}: {label_family_id}")

        candidate_family_pool = _parse_candidate_family_pool(
            raw_row.get("candidate_family_pool"),
            str(raw_row.get("candidate_family_pool_joined") or ""),
        )
        _validate_candidate_family_pool(
            problem_id=problem_id,
            candidate_family_pool=candidate_family_pool,
            label_family_id=label_family_id,
        )

        primary_family_id = candidate_family_pool[0]
        fallback_family_id = candidate_family_pool[1] if len(candidate_family_pool) > 1 else ""
        label_cohort = derive_label_cohort(str(raw_row.get("source_path") or ""))

        curated_row = CuratedSelectorRow(
            problem_id=problem_id,
            label_family_id=label_family_id,
            label_cohort=label_cohort,
            primary_family_id=primary_family_id,
            fallback_family_id=fallback_family_id,
            candidate_family_pool=candidate_family_pool,
            raw_features=_normalize_allowed_features(
                raw_row,
                candidate_family_pool,
                primary_family_id,
                fallback_family_id,
            ),
            source_path=str(raw_row.get("source_path") or ""),
        )
        by_problem_id[problem_id].append(curated_row)

    cohort_ranks = _cohort_rank_map(cohort_priority)
    curated_rows: list[CuratedSelectorRow] = []
    default_rank = len(cohort_priority)

    for problem_id in sorted(by_problem_id):
        problem_rows = by_problem_id[problem_id]
        best_rank = min(cohort_ranks.get(row.label_cohort, default_rank) for row in problem_rows)
        kept_rows = [
            row
            for row in problem_rows
            if cohort_ranks.get(row.label_cohort, default_rank) == best_rank
        ]
        labels = {row.label_family_id for row in kept_rows}
        if len(labels) > 1:
            chosen_cohort = kept_rows[0].label_cohort if kept_rows else "unknown"
            label_text = ", ".join(sorted(labels))
            raise ValueError(
                f"same-priority label conflict for problem_id={problem_id} cohort={chosen_cohort}: {label_text}"
            )
        feature_signatures = {_allowlisted_feature_signature(row) for row in kept_rows}
        if len(feature_signatures) > 1:
            chosen_cohort = kept_rows[0].label_cohort if kept_rows else "unknown"
            raise ValueError(
                f"same-label feature mismatch for problem_id={problem_id} cohort={chosen_cohort}"
            )
        curated_rows.append(
            sorted(
                kept_rows,
                key=lambda row: (
                    row.source_path,
                    row.label_family_id,
                    row.primary_family_id,
                    row.fallback_family_id,
                ),
            )[0]
        )

    return curated_rows


def _build_numeric_stats(rows: list[CuratedSelectorRow]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for source_name, feature_name in NUMERIC_FEATURE_NAMES.items():
        values = np.array(
            [
                math.log1p(max(_coerce_int(row.raw_features.get(source_name, 0)), 0))
                for row in rows
            ],
            dtype=np.float64,
        )
        mean = float(values.mean()) if len(values) else 0.0
        std = float(values.std()) if len(values) else 1.0
        if std <= 1e-9:
            std = 1.0
        stats[feature_name] = {"mean": mean, "std": std}
    return stats


def _extract_row_feature_map(
    row: CuratedSelectorRow,
    numeric_stats: dict[str, dict[str, float]],
) -> dict[str, float]:
    feature_map: dict[str, float] = {"bias": 1.0}

    tag_text = row.raw_features["canonical_tags_joined"] or row.raw_features["problem_tags_joined"]
    for tag in _split_joined(tag_text):
        feature_map[f"tag::{tag}"] = 1.0

    if row.primary_family_id:
        feature_map[f"family::primary::{row.primary_family_id}"] = 1.0
    if row.fallback_family_id:
        feature_map[f"family::fallback::{row.fallback_family_id}"] = 1.0

    pool_joined = str(row.raw_features["candidate_family_pool_joined"] or "")
    if pool_joined:
        feature_map[f"family::pool::{pool_joined}"] = 1.0

    for source_name, feature_name in NUMERIC_FEATURE_NAMES.items():
        raw_value = max(_coerce_int(row.raw_features.get(source_name, 0)), 0)
        transformed = math.log1p(raw_value)
        stats = numeric_stats[feature_name]
        feature_map[feature_name] = (transformed - stats["mean"]) / stats["std"]

    return feature_map


def build_feature_frame(
    rows: list[CuratedSelectorRow],
    fitted_vocab: dict[str, int] | None = None,
    numeric_stats: dict[str, dict[str, float]] | None = None,
) -> FeatureFrame:
    if numeric_stats is None:
        numeric_stats = _build_numeric_stats(rows)

    row_feature_maps = [_extract_row_feature_map(row, numeric_stats) for row in rows]

    if fitted_vocab is None:
        feature_names = tuple(sorted({name for feature_map in row_feature_maps for name in feature_map}))
        feature_vocab = {name: index for index, name in enumerate(feature_names)}
    else:
        feature_vocab = dict(fitted_vocab)
        feature_names = tuple(name for name, _ in sorted(feature_vocab.items(), key=lambda item: item[1]))

    matrix = np.zeros((len(rows), len(feature_vocab)), dtype=np.float64)
    for row_index, feature_map in enumerate(row_feature_maps):
        for feature_name, feature_value in feature_map.items():
            feature_index = feature_vocab.get(feature_name)
            if feature_index is None:
                continue
            matrix[row_index, feature_index] = feature_value

    labels = np.array([LABEL_TO_TARGET[row.label_family_id] for row in rows], dtype=np.float64)
    return FeatureFrame(
        matrix=matrix,
        labels=labels,
        feature_names=feature_names,
        feature_vocab=feature_vocab,
        numeric_stats=numeric_stats,
    )


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def _fit_binary_logreg(
    X: np.ndarray,
    y: np.ndarray,
    *,
    learning_rate: float = 0.1,
    steps: int = 400,
    l2: float = 0.01,
) -> np.ndarray:
    weights = np.zeros(X.shape[1], dtype=np.float64)
    bias_index = None
    if X.shape[1] > 0:
        bias_index = 0
    for _ in range(steps):
        probs = _sigmoid(X @ weights)
        gradient = (X.T @ (probs - y)) / max(len(y), 1)
        regularization = l2 * weights
        if bias_index is not None:
            regularization[bias_index] = 0.0
        gradient += regularization
        weights -= learning_rate * gradient
    return weights


def fit_selector_prior(rows: list[CuratedSelectorRow]) -> SelectorPriorModel:
    if not rows:
        raise ValueError("cannot fit selector prior with zero rows")
    frame = build_feature_frame(rows)
    weights = _fit_binary_logreg(frame.matrix, frame.labels)
    return SelectorPriorModel(
        feature_names=frame.feature_names,
        feature_vocab=frame.feature_vocab,
        weights=weights,
        numeric_stats=frame.numeric_stats,
        label_mapping=dict(LABEL_TO_TARGET),
        learning_rate=0.1,
        steps=400,
        l2=0.01,
    )


def predict_selector_prior(model: SelectorPriorModel, rows: list[CuratedSelectorRow]) -> list[PredictionRow]:
    frame = build_feature_frame(
        rows,
        fitted_vocab=model.feature_vocab,
        numeric_stats=model.numeric_stats,
    )
    if len(rows) == 0:
        return []
    probabilities = _sigmoid(frame.matrix @ model.weights)
    predictions: list[PredictionRow] = []
    for row, probability in zip(rows, probabilities):
        predicted_family_id = TARGET_TO_LABEL[int(probability >= 0.5)]
        always_primary_prediction = row.primary_family_id
        always_enumeration_prediction = "oracle.enumeration.n_nested_loops"
        always_dp_prediction = "oracle.dp.topdown"
        predictions.append(
            PredictionRow(
                problem_id=row.problem_id,
                label_family_id=row.label_family_id,
                predicted_family_id=predicted_family_id,
                predicted_dp_probability=float(probability),
                primary_family_id=row.primary_family_id,
                fallback_family_id=row.fallback_family_id,
                label_cohort=row.label_cohort,
                model_correct=int(predicted_family_id == row.label_family_id),
                always_primary_prediction=always_primary_prediction,
                always_primary_correct=int(always_primary_prediction == row.label_family_id),
                always_enumeration_prediction=always_enumeration_prediction,
                always_enumeration_correct=int(always_enumeration_prediction == row.label_family_id),
                always_dp_prediction=always_dp_prediction,
                always_dp_correct=int(always_dp_prediction == row.label_family_id),
            )
        )
    return predictions


def evaluate_selector_prior(
    rows: list[CuratedSelectorRow],
    eval_protocol: str = "leave_one_problem_out",
) -> dict[str, object]:
    if eval_protocol != "leave_one_problem_out":
        raise ValueError(f"unsupported eval_protocol: {eval_protocol}")

    by_problem_id: dict[str, list[CuratedSelectorRow]] = defaultdict(list)
    for row in rows:
        by_problem_id[row.problem_id].append(row)

    predictions: list[PredictionRow] = []
    for problem_id in sorted(by_problem_id):
        holdout_rows = by_problem_id[problem_id]
        train_rows = [
            candidate
            for other_problem_id, grouped_rows in by_problem_id.items()
            if other_problem_id != problem_id
            for candidate in grouped_rows
        ]
        if not train_rows:
            for row in holdout_rows:
                primary_prediction = row.primary_family_id
                predicted_dp_probability = (
                    1.0 if primary_prediction == "oracle.dp.topdown" else 0.0
                )
                predictions.append(
                    PredictionRow(
                        problem_id=row.problem_id,
                        label_family_id=row.label_family_id,
                        predicted_family_id=primary_prediction,
                        predicted_dp_probability=predicted_dp_probability,
                        primary_family_id=row.primary_family_id,
                        fallback_family_id=row.fallback_family_id,
                        label_cohort=row.label_cohort,
                        model_correct=int(primary_prediction == row.label_family_id),
                        always_primary_prediction=primary_prediction,
                        always_primary_correct=int(primary_prediction == row.label_family_id),
                        always_enumeration_prediction="oracle.enumeration.n_nested_loops",
                        always_enumeration_correct=int(
                            row.label_family_id == "oracle.enumeration.n_nested_loops"
                        ),
                        always_dp_prediction="oracle.dp.topdown",
                        always_dp_correct=int(row.label_family_id == "oracle.dp.topdown"),
                    )
                )
            continue

        fold_model = fit_selector_prior(train_rows)
        predictions.extend(predict_selector_prior(fold_model, holdout_rows))

    prediction_dicts = [asdict(prediction) for prediction in predictions]
    total = len(predictions)
    summary = {
        "eval_protocol": eval_protocol,
        "num_examples": len(rows),
        "num_unique_problem_ids": len(by_problem_id),
        "num_folds": len(by_problem_id),
        "label_distribution": dict(Counter(row.label_family_id for row in rows)),
        "cohort_distribution": dict(Counter(row.label_cohort for row in rows)),
        "model_accuracy": sum(prediction.model_correct for prediction in predictions) / total if total else 0.0,
        "always_primary_accuracy": (
            sum(prediction.always_primary_correct for prediction in predictions) / total if total else 0.0
        ),
        "always_enumeration_accuracy": (
            sum(prediction.always_enumeration_correct for prediction in predictions) / total if total else 0.0
        ),
        "always_dp_accuracy": (
            sum(prediction.always_dp_correct for prediction in predictions) / total if total else 0.0
        ),
    }
    return {
        "summary": summary,
        "predictions": prediction_dicts,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_training_metadata(
    *,
    input_csv: Path,
    rows: list[CuratedSelectorRow],
    cohort_priority: tuple[str, ...],
    eval_protocol: str,
) -> dict[str, Any]:
    return {
        "trusted_csv_path": str(input_csv.resolve()),
        "trusted_csv_sha256": _sha256_file(input_csv),
        "num_examples": len(rows),
        "problem_ids": sorted({row.problem_id for row in rows}),
        "label_distribution": dict(Counter(row.label_family_id for row in rows)),
        "cohort_priority": list(cohort_priority),
        "eval_protocol": eval_protocol,
    }


def write_selector_prior_artifacts(
    *,
    rows: list[CuratedSelectorRow],
    model: SelectorPriorModel,
    evaluation: dict[str, object],
    training_metadata: dict[str, Any],
    output_dir: Path,
    prefix: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    curated_examples_path = output_dir / f"{prefix}_curated_examples.csv"
    model_path = output_dir / f"{prefix}_model.json"
    feature_weights_path = output_dir / f"{prefix}_feature_weights.csv"
    eval_predictions_path = output_dir / f"{prefix}_eval_predictions.csv"
    eval_summary_path = output_dir / f"{prefix}_eval_summary.json"

    curated_rows_for_csv = []
    for row in rows:
        curated_rows_for_csv.append(
            {
                "problem_id": row.problem_id,
                "label_family_id": row.label_family_id,
                "label_cohort": row.label_cohort,
                "primary_family_id": row.primary_family_id,
                "fallback_family_id": row.fallback_family_id,
                "candidate_family_pool": json.dumps(list(row.candidate_family_pool), ensure_ascii=False),
                "candidate_family_pool_joined": row.raw_features["candidate_family_pool_joined"],
                "problem_tags_joined": row.raw_features["problem_tags_joined"],
                "canonical_tags_joined": row.raw_features["canonical_tags_joined"],
                "problem_type_joined": row.raw_features["problem_type_joined"],
                "key_elements_joined": row.raw_features["key_elements_joined"],
                "objective_text": row.raw_features["objective_text"],
                "graph_type": row.raw_features["graph_type"],
                "is_multi_solution": int(bool(row.raw_features["is_multi_solution"])),
                "data_structures_joined": row.raw_features["data_structures_joined"],
                "constraints_json": row.raw_features["constraints_json"],
                "description_chars": row.raw_features["description_chars"],
                "public_tests_count": row.raw_features["public_tests_count"],
                "source_path": row.source_path,
            }
        )
    _write_csv(
        curated_examples_path,
        curated_rows_for_csv,
        fieldnames=[
            "problem_id",
            "label_family_id",
            "label_cohort",
            "primary_family_id",
            "fallback_family_id",
            "candidate_family_pool",
            "candidate_family_pool_joined",
            "problem_tags_joined",
            "canonical_tags_joined",
            "problem_type_joined",
            "key_elements_joined",
            "objective_text",
            "graph_type",
            "is_multi_solution",
            "data_structures_joined",
            "constraints_json",
            "description_chars",
            "public_tests_count",
            "source_path",
        ],
    )

    model_payload = {
        "feature_names": list(model.feature_names),
        "weights": [float(weight) for weight in model.weights],
        "numeric_stats": model.numeric_stats,
        "label_mapping": model.label_mapping,
        "learning_rate": model.learning_rate,
        "steps": model.steps,
        "l2": model.l2,
        "training_metadata": training_metadata,
    }
    model_path.write_text(json.dumps(model_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    feature_weight_rows = [
        {
            "feature_name": feature_name,
            "weight": float(model.weights[index]),
            "abs_weight": abs(float(model.weights[index])),
        }
        for index, feature_name in enumerate(model.feature_names)
    ]
    feature_weight_rows.sort(key=lambda row: (-row["abs_weight"], row["feature_name"]))
    _write_csv(
        feature_weights_path,
        feature_weight_rows,
        fieldnames=["feature_name", "weight", "abs_weight"],
    )

    prediction_rows = list(evaluation["predictions"])
    _write_csv(
        eval_predictions_path,
        prediction_rows,
        fieldnames=[
            "problem_id",
            "label_family_id",
            "predicted_family_id",
            "predicted_dp_probability",
            "primary_family_id",
            "fallback_family_id",
            "label_cohort",
            "model_correct",
            "always_primary_prediction",
            "always_primary_correct",
            "always_enumeration_prediction",
            "always_enumeration_correct",
            "always_dp_prediction",
            "always_dp_correct",
        ],
    )

    eval_summary_path.write_text(
        json.dumps(evaluation["summary"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "curated_examples_csv": curated_examples_path,
        "model_json": model_path,
        "feature_weights_csv": feature_weights_path,
        "eval_predictions_csv": eval_predictions_path,
        "eval_summary_json": eval_summary_path,
    }


def train_selector_prior_pipeline(
    *,
    input_csv: Path,
    output_dir: Path,
    prefix: str,
    cohort_priority: tuple[str, ...] = DEFAULT_COHORT_PRIORITY,
    eval_protocol: str = "leave_one_problem_out",
) -> dict[str, object]:
    trusted_rows = load_selector_prior_rows(input_csv)
    curated_rows = build_curated_training_rows(trusted_rows, cohort_priority=cohort_priority)
    evaluation = evaluate_selector_prior(curated_rows, eval_protocol=eval_protocol)
    model = fit_selector_prior(curated_rows)
    training_metadata = _build_training_metadata(
        input_csv=input_csv,
        rows=curated_rows,
        cohort_priority=cohort_priority,
        eval_protocol=eval_protocol,
    )
    artifacts = write_selector_prior_artifacts(
        rows=curated_rows,
        model=model,
        evaluation=evaluation,
        training_metadata=training_metadata,
        output_dir=output_dir,
        prefix=prefix,
    )
    return {
        "rows": curated_rows,
        "evaluation": evaluation,
        "model": model,
        "training_metadata": training_metadata,
        "artifacts": artifacts,
    }
