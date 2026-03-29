from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.oracle.selector_prior import (
    CuratedSelectorRow,
    LABEL_TO_TARGET,
    NUMERIC_FEATURE_NAMES,
    TARGET_TO_LABEL,
    _build_training_metadata,
    _coerce_bool,
    _coerce_int,
    _split_joined,
    build_curated_training_rows,
    load_selector_prior_rows,
    predict_selector_prior,
)
from src.oracle.selector_prior_diagnostics import (
    predict_rule_has_math,
    predict_rule_small_math_pattern,
)
from src.oracle.selector_prior_holdout import (
    _compute_baseline_metrics,
    _validate_model_provenance,
    load_selector_prior_model,
)


DEFAULT_POSITIVE_CLASS_WEIGHTS = (1.0, 1.25, 1.5, 2.0)
DEFAULT_OBJECTIVE_TEXT_VOCAB_CAPS = (0, 50, 100)
DEFAULT_THRESHOLD_GRID = tuple(round(value, 2) for value in np.arange(0.20, 0.801, 0.05))
DEFAULT_SUCCESS_CRITERIA = {
    "balanced_accuracy_must_exceed": ["always_dp", "rule_has_math"],
    "min_accuracy_delta_vs_always_dp": -0.02,
    "min_dp_recall": 0.85,
}

DP_FAMILY_ID = "oracle.dp.topdown"
ENUMERATION_FAMILY_ID = "oracle.enumeration.n_nested_loops"
WEIGHTED_LABEL_FAMILY_ID = ENUMERATION_FAMILY_ID


@dataclass(frozen=True)
class SelectorPriorV2FeatureSwitches:
    use_problem_type_bag: bool = True
    use_key_elements_bag: bool = True
    use_graph_type: bool = True
    use_data_structures_bag: bool = True
    use_is_multi_solution: bool = True
    objective_text_vocab_cap: int = 0


@dataclass(frozen=True)
class SelectorPriorV2FeatureFrame:
    matrix: np.ndarray
    labels: np.ndarray
    feature_names: tuple[str, ...]
    feature_vocab: dict[str, int]
    numeric_stats: dict[str, dict[str, float]]
    objective_text_vocabulary: tuple[str, ...]


@dataclass(frozen=True)
class SelectorPriorV2Model:
    feature_names: tuple[str, ...]
    feature_vocab: dict[str, int]
    weights: np.ndarray
    numeric_stats: dict[str, dict[str, float]]
    objective_text_vocabulary: tuple[str, ...]
    feature_switches: SelectorPriorV2FeatureSwitches
    label_mapping: dict[str, int]
    learning_rate: float
    steps: int
    l2: float
    positive_class_weight: float
    decision_threshold: float
    training_metadata: dict[str, Any] | None = None
    selection_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SelectorPriorV2PredictionRow:
    problem_id: str
    label_family_id: str
    predicted_family_id: str
    predicted_dp_probability: float
    decision_threshold: float
    primary_family_id: str
    fallback_family_id: str
    label_cohort: str
    model_correct: int


def _tokenize_objective_text(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) >= 2]


def _fit_objective_text_vocabulary(
    rows: list[CuratedSelectorRow],
    *,
    vocab_cap: int,
) -> tuple[str, ...]:
    if vocab_cap <= 0:
        return ()
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(set(_tokenize_objective_text(str(row.raw_features.get("objective_text") or ""))))
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(token for token, _ in ranked[:vocab_cap])


def _build_numeric_stats(rows: list[CuratedSelectorRow]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for source_name, feature_name in NUMERIC_FEATURE_NAMES.items():
        values = np.array(
            [math.log1p(max(_coerce_int(row.raw_features.get(source_name, 0)), 0)) for row in rows],
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
    *,
    numeric_stats: dict[str, dict[str, float]],
    feature_switches: SelectorPriorV2FeatureSwitches,
    objective_text_vocabulary: tuple[str, ...],
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

    joined_fields = (
        ("problem_type_joined", feature_switches.use_problem_type_bag),
        ("key_elements_joined", feature_switches.use_key_elements_bag),
        ("data_structures_joined", feature_switches.use_data_structures_bag),
    )
    for field_name, enabled in joined_fields:
        if not enabled:
            continue
        for value in _split_joined(row.raw_features.get(field_name, "")):
            feature_map[f"joined::{field_name.removesuffix('_joined')}::{value}"] = 1.0

    if feature_switches.use_graph_type:
        graph_type = str(row.raw_features.get("graph_type") or "").strip()
        if graph_type:
            feature_map[f"graph_type::{graph_type}"] = 1.0

    if feature_switches.use_is_multi_solution:
        feature_map["flag::is_multi_solution"] = float(bool(_coerce_bool(row.raw_features.get("is_multi_solution"))))

    if feature_switches.objective_text_vocab_cap > 0 and objective_text_vocabulary:
        allowed_tokens = set(objective_text_vocabulary)
        for token in set(_tokenize_objective_text(str(row.raw_features.get("objective_text") or ""))):
            if token in allowed_tokens:
                feature_map[f"objective::{token}"] = 1.0

    for source_name, feature_name in NUMERIC_FEATURE_NAMES.items():
        raw_value = max(_coerce_int(row.raw_features.get(source_name, 0)), 0)
        transformed = math.log1p(raw_value)
        stats = numeric_stats[feature_name]
        feature_map[feature_name] = (transformed - stats["mean"]) / stats["std"]

    return feature_map


def build_feature_frame_v2(
    rows: list[CuratedSelectorRow],
    *,
    feature_switches: SelectorPriorV2FeatureSwitches | None = None,
    fitted_vocab: dict[str, int] | None = None,
    numeric_stats: dict[str, dict[str, float]] | None = None,
    objective_text_vocabulary: tuple[str, ...] | None = None,
) -> SelectorPriorV2FeatureFrame:
    feature_switches = feature_switches or SelectorPriorV2FeatureSwitches()
    if numeric_stats is None:
        numeric_stats = _build_numeric_stats(rows)
    if objective_text_vocabulary is None:
        objective_text_vocabulary = _fit_objective_text_vocabulary(
            rows,
            vocab_cap=feature_switches.objective_text_vocab_cap,
        )

    row_feature_maps = [
        _extract_row_feature_map(
            row,
            numeric_stats=numeric_stats,
            feature_switches=feature_switches,
            objective_text_vocabulary=objective_text_vocabulary,
        )
        for row in rows
    ]

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
    return SelectorPriorV2FeatureFrame(
        matrix=matrix,
        labels=labels,
        feature_names=feature_names,
        feature_vocab=feature_vocab,
        numeric_stats=numeric_stats,
        objective_text_vocabulary=objective_text_vocabulary,
    )


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def _fit_weighted_binary_logreg(
    X: np.ndarray,
    y: np.ndarray,
    *,
    positive_class_weight: float = 1.0,
    learning_rate: float = 0.1,
    steps: int = 400,
    l2: float = 0.01,
) -> np.ndarray:
    weights = np.zeros(X.shape[1], dtype=np.float64)
    sample_weights = np.where(y == float(LABEL_TO_TARGET[WEIGHTED_LABEL_FAMILY_ID]), positive_class_weight, 1.0)
    denominator = float(sample_weights.sum()) if len(sample_weights) else 1.0
    bias_index = 0 if X.shape[1] > 0 else None
    for _ in range(steps):
        probs = _sigmoid(X @ weights)
        gradient = (X.T @ ((probs - y) * sample_weights)) / denominator
        regularization = l2 * weights
        if bias_index is not None:
            regularization[bias_index] = 0.0
        gradient += regularization
        weights -= learning_rate * gradient
    return weights


def fit_selector_prior_v2(
    rows: list[CuratedSelectorRow],
    *,
    positive_class_weight: float = 1.0,
    feature_switches: SelectorPriorV2FeatureSwitches | None = None,
    decision_threshold: float = 0.5,
    training_metadata: dict[str, Any] | None = None,
    selection_metadata: dict[str, Any] | None = None,
) -> SelectorPriorV2Model:
    if not rows:
        raise ValueError("cannot fit selector prior v2 with zero rows")
    feature_switches = feature_switches or SelectorPriorV2FeatureSwitches()
    frame = build_feature_frame_v2(rows, feature_switches=feature_switches)
    weights = _fit_weighted_binary_logreg(
        frame.matrix,
        frame.labels,
        positive_class_weight=positive_class_weight,
    )
    return SelectorPriorV2Model(
        feature_names=frame.feature_names,
        feature_vocab=frame.feature_vocab,
        weights=weights,
        numeric_stats=frame.numeric_stats,
        objective_text_vocabulary=frame.objective_text_vocabulary,
        feature_switches=feature_switches,
        label_mapping=dict(LABEL_TO_TARGET),
        learning_rate=0.1,
        steps=400,
        l2=0.01,
        positive_class_weight=float(positive_class_weight),
        decision_threshold=float(decision_threshold),
        training_metadata=training_metadata,
        selection_metadata=selection_metadata,
    )


def predict_selector_prior_v2(
    model: SelectorPriorV2Model,
    rows: list[CuratedSelectorRow],
    *,
    decision_threshold: float | None = None,
) -> list[SelectorPriorV2PredictionRow]:
    if not rows:
        return []
    frame = build_feature_frame_v2(
        rows,
        feature_switches=model.feature_switches,
        fitted_vocab=model.feature_vocab,
        numeric_stats=model.numeric_stats,
        objective_text_vocabulary=model.objective_text_vocabulary,
    )
    probabilities = _sigmoid(frame.matrix @ model.weights)
    threshold = float(model.decision_threshold if decision_threshold is None else decision_threshold)
    predictions: list[SelectorPriorV2PredictionRow] = []
    for row, probability in zip(rows, probabilities):
        predicted_family_id = TARGET_TO_LABEL[int(probability >= threshold)]
        predictions.append(
            SelectorPriorV2PredictionRow(
                problem_id=row.problem_id,
                label_family_id=row.label_family_id,
                predicted_family_id=predicted_family_id,
                predicted_dp_probability=float(probability),
                decision_threshold=threshold,
                primary_family_id=row.primary_family_id,
                fallback_family_id=row.fallback_family_id,
                label_cohort=row.label_cohort,
                model_correct=int(predicted_family_id == row.label_family_id),
            )
        )
    return predictions


def compute_selector_prior_v2_oof_predictions(
    rows: list[CuratedSelectorRow],
    *,
    positive_class_weight: float,
    feature_switches: SelectorPriorV2FeatureSwitches,
    return_fold_models: bool = False,
) -> dict[str, Any]:
    by_problem_id: dict[str, list[CuratedSelectorRow]] = defaultdict(list)
    for row in rows:
        by_problem_id[row.problem_id].append(row)

    prediction_rows: list[dict[str, Any]] = []
    fold_models: dict[str, SelectorPriorV2Model] = {}
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
                predicted_dp_probability = 1.0 if row.primary_family_id == DP_FAMILY_ID else 0.0
                prediction_rows.append(
                    {
                        "problem_id": row.problem_id,
                        "label_family_id": row.label_family_id,
                        "label_cohort": row.label_cohort,
                        "predicted_dp_probability": predicted_dp_probability,
                        "primary_family_id": row.primary_family_id,
                        "fallback_family_id": row.fallback_family_id,
                    }
                )
            continue

        fold_model = fit_selector_prior_v2(
            train_rows,
            positive_class_weight=positive_class_weight,
            feature_switches=feature_switches,
        )
        if return_fold_models:
            fold_models[problem_id] = fold_model
        for prediction in predict_selector_prior_v2(fold_model, holdout_rows, decision_threshold=0.5):
            prediction_rows.append(
                {
                    "problem_id": prediction.problem_id,
                    "label_family_id": prediction.label_family_id,
                    "label_cohort": prediction.label_cohort,
                    "predicted_dp_probability": prediction.predicted_dp_probability,
                    "primary_family_id": prediction.primary_family_id,
                    "fallback_family_id": prediction.fallback_family_id,
                }
            )

    result: dict[str, Any] = {"predictions": prediction_rows}
    if return_fold_models:
        result["fold_models"] = fold_models
    return result


def _threshold_candidates(probabilities: list[float], threshold_grid: tuple[float, ...]) -> list[float]:
    candidates = {float(round(value, 12)) for value in threshold_grid}
    for probability in probabilities:
        if 0.0 <= probability <= 1.0:
            candidates.add(float(round(probability, 12)))
    return sorted(candidates)


def _prediction_labels_from_probabilities(probabilities: list[float], threshold: float) -> list[str]:
    return [TARGET_TO_LABEL[int(probability >= threshold)] for probability in probabilities]


def _single_example_balanced_accuracy_swing_threshold(actual_labels: list[str]) -> float:
    num_dp = sum(1 for label in actual_labels if label == DP_FAMILY_ID)
    num_enumeration = sum(1 for label in actual_labels if label == ENUMERATION_FAMILY_ID)
    candidates = []
    if num_dp:
        candidates.append(1.0 / (2.0 * num_dp))
    if num_enumeration:
        candidates.append(1.0 / (2.0 * num_enumeration))
    return max(candidates) if candidates else 0.0


def _candidate_rank_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -candidate["balanced_accuracy"],
        -candidate["accuracy"],
        -candidate["dp_recall"],
        candidate["positive_class_weight"],
        abs(candidate["threshold"] - 0.5),
        candidate["feature_switches"]["objective_text_vocab_cap"],
        candidate["threshold"],
    )


def select_selector_prior_v2_configuration(
    rows: list[CuratedSelectorRow],
    *,
    positive_class_weights: tuple[float, ...] = DEFAULT_POSITIVE_CLASS_WEIGHTS,
    objective_text_vocab_caps: tuple[int, ...] = DEFAULT_OBJECTIVE_TEXT_VOCAB_CAPS,
    threshold_grid: tuple[float, ...] = DEFAULT_THRESHOLD_GRID,
) -> dict[str, Any]:
    candidate_results: list[dict[str, Any]] = []
    best_oof_predictions: list[dict[str, Any]] = []

    for objective_text_vocab_cap in objective_text_vocab_caps:
        feature_switches = SelectorPriorV2FeatureSwitches(objective_text_vocab_cap=objective_text_vocab_cap)
        for positive_class_weight in positive_class_weights:
            oof_result = compute_selector_prior_v2_oof_predictions(
                rows,
                positive_class_weight=positive_class_weight,
                feature_switches=feature_switches,
            )
            probabilities = [
                float(prediction["predicted_dp_probability"])
                for prediction in sorted(oof_result["predictions"], key=lambda item: item["problem_id"])
            ]
            actual_labels = [
                str(prediction["label_family_id"])
                for prediction in sorted(oof_result["predictions"], key=lambda item: item["problem_id"])
            ]
            for threshold in _threshold_candidates(probabilities, threshold_grid):
                predicted_labels = _prediction_labels_from_probabilities(probabilities, threshold)
                metrics = _compute_baseline_metrics(actual_labels, predicted_labels)
                candidate_results.append(
                    {
                        "positive_class_weight": float(positive_class_weight),
                        "threshold": float(threshold),
                        "feature_switches": asdict(feature_switches),
                        "objective_text_vocab_cap": objective_text_vocab_cap,
                        "balanced_accuracy": metrics["balanced_accuracy"],
                        "accuracy": metrics["accuracy"],
                        "dp_recall": metrics["dp_recall"],
                        "enumeration_recall": metrics["enumeration_recall"],
                        "confusion_matrix": metrics["confusion_matrix"],
                    }
                )

            if not best_oof_predictions:
                best_oof_predictions = list(oof_result["predictions"])

    if not candidate_results:
        raise ValueError("selector prior v2 candidate search produced zero results")

    best_candidate = min(candidate_results, key=_candidate_rank_key)
    chosen_feature_switches = SelectorPriorV2FeatureSwitches(
        objective_text_vocab_cap=int(best_candidate["feature_switches"]["objective_text_vocab_cap"])
    )
    chosen_oof_result = compute_selector_prior_v2_oof_predictions(
        rows,
        positive_class_weight=float(best_candidate["positive_class_weight"]),
        feature_switches=chosen_feature_switches,
    )
    chosen_oof_probabilities = {
        prediction["problem_id"]: float(prediction["predicted_dp_probability"])
        for prediction in chosen_oof_result["predictions"]
    }
    oof_predictions: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item.problem_id):
        probability = chosen_oof_probabilities[row.problem_id]
        predicted_family_id = TARGET_TO_LABEL[int(probability >= float(best_candidate["threshold"]))]
        oof_predictions.append(
            {
                "problem_id": row.problem_id,
                "label_family_id": row.label_family_id,
                "label_cohort": row.label_cohort,
                "predicted_dp_probability": probability,
                "predicted_family_id": predicted_family_id,
                "decision_threshold": float(best_candidate["threshold"]),
                "model_correct": int(predicted_family_id == row.label_family_id),
            }
        )

    actual_labels = [row.label_family_id for row in sorted(rows, key=lambda item: item.problem_id)]
    selection_summary = {
        "evaluation_kind": "dev_lopo_oof_model_selection",
        "num_examples": len(rows),
        "num_unique_problem_ids": len({row.problem_id for row in rows}),
        "label_distribution": dict(Counter(actual_labels)),
        "selection_protocol": {
            "eval_protocol": "leave_one_problem_out",
            "vocab_fitting_scope": "fold_train_only",
            "threshold_source": "oof_probabilities_plus_fixed_grid",
            "uses_external_holdout": False,
            "final_refit_threshold_policy": "reuse_frozen_oof_threshold",
            "tie_break_order": [
                "balanced_accuracy",
                "accuracy",
                "dp_recall",
                "smaller_positive_class_weight",
                "threshold_closer_to_0.5",
                "smaller_objective_text_vocab_cap",
            ],
        },
        "weighted_label_family_id": WEIGHTED_LABEL_FAMILY_ID,
        "candidate_search_space": {
            "positive_class_weights": [float(value) for value in positive_class_weights],
            "objective_text_vocab_caps": [int(value) for value in objective_text_vocab_caps],
            "fixed_threshold_grid": [float(value) for value in threshold_grid],
        },
        "candidate_results": sorted(candidate_results, key=_candidate_rank_key),
        "chosen_positive_class_weight": float(best_candidate["positive_class_weight"]),
        "chosen_threshold": float(best_candidate["threshold"]),
        "chosen_feature_switches": dict(best_candidate["feature_switches"]),
        "chosen_metrics": {
            "accuracy": best_candidate["accuracy"],
            "balanced_accuracy": best_candidate["balanced_accuracy"],
            "dp_recall": best_candidate["dp_recall"],
            "enumeration_recall": best_candidate["enumeration_recall"],
            "confusion_matrix": best_candidate["confusion_matrix"],
        },
        "success_criteria": dict(DEFAULT_SUCCESS_CRITERIA),
        "single_example_balanced_accuracy_swing_threshold": _single_example_balanced_accuracy_swing_threshold(
            actual_labels
        ),
        "final_refit_uses_frozen_threshold": True,
    }
    return {
        "selection_summary": selection_summary,
        "oof_predictions": oof_predictions,
        "chosen_feature_switches": chosen_feature_switches,
        "chosen_positive_class_weight": float(best_candidate["positive_class_weight"]),
        "chosen_threshold": float(best_candidate["threshold"]),
    }


def _model_payload(model: SelectorPriorV2Model) -> dict[str, Any]:
    return {
        "feature_names": list(model.feature_names),
        "weights": [float(weight) for weight in model.weights],
        "numeric_stats": model.numeric_stats,
        "objective_text_vocabulary": list(model.objective_text_vocabulary),
        "feature_switches": asdict(model.feature_switches),
        "label_mapping": model.label_mapping,
        "learning_rate": model.learning_rate,
        "steps": model.steps,
        "l2": model.l2,
        "positive_class_weight": model.positive_class_weight,
        "decision_threshold": model.decision_threshold,
        "training_metadata": model.training_metadata,
        "selection_metadata": model.selection_metadata,
    }


def load_selector_prior_v2_model(model_json_path: Path) -> SelectorPriorV2Model:
    payload = json.loads(model_json_path.read_text(encoding="utf-8"))
    feature_names = tuple(str(name) for name in payload["feature_names"])
    feature_vocab = {name: index for index, name in enumerate(feature_names)}
    feature_switches_payload = dict(payload.get("feature_switches") or {})
    return SelectorPriorV2Model(
        feature_names=feature_names,
        feature_vocab=feature_vocab,
        weights=np.array(payload["weights"], dtype=np.float64),
        numeric_stats=dict(payload["numeric_stats"]),
        objective_text_vocabulary=tuple(str(token) for token in payload.get("objective_text_vocabulary", [])),
        feature_switches=SelectorPriorV2FeatureSwitches(
            use_problem_type_bag=bool(feature_switches_payload.get("use_problem_type_bag", True)),
            use_key_elements_bag=bool(feature_switches_payload.get("use_key_elements_bag", True)),
            use_graph_type=bool(feature_switches_payload.get("use_graph_type", True)),
            use_data_structures_bag=bool(feature_switches_payload.get("use_data_structures_bag", True)),
            use_is_multi_solution=bool(feature_switches_payload.get("use_is_multi_solution", True)),
            objective_text_vocab_cap=int(feature_switches_payload.get("objective_text_vocab_cap", 0)),
        ),
        label_mapping={str(key): int(value) for key, value in payload["label_mapping"].items()},
        learning_rate=float(payload.get("learning_rate", 0.1)),
        steps=int(payload.get("steps", 400)),
        l2=float(payload.get("l2", 0.01)),
        positive_class_weight=float(payload.get("positive_class_weight", 1.0)),
        decision_threshold=float(payload.get("decision_threshold", 0.5)),
        training_metadata=dict(payload.get("training_metadata") or {}),
        selection_metadata=dict(payload.get("selection_metadata") or {}),
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_selector_prior_v2_training_artifacts(
    *,
    model: SelectorPriorV2Model,
    selection_summary: dict[str, Any],
    oof_predictions: list[dict[str, Any]],
    output_dir: Path,
    prefix: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / f"{prefix}_model.json"
    feature_weights_path = output_dir / f"{prefix}_feature_weights.csv"
    oof_predictions_path = output_dir / f"{prefix}_oof_predictions.csv"
    selection_summary_path = output_dir / f"{prefix}_selection_summary.json"

    model_path.write_text(
        json.dumps(_model_payload(model), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    feature_weight_rows = [
        {
            "feature_name": feature_name,
            "weight": float(model.weights[index]),
            "abs_weight": abs(float(model.weights[index])),
        }
        for index, feature_name in enumerate(model.feature_names)
    ]
    feature_weight_rows.sort(key=lambda row: (-row["abs_weight"], row["feature_name"]))
    _write_csv(feature_weights_path, feature_weight_rows, ["feature_name", "weight", "abs_weight"])

    _write_csv(
        oof_predictions_path,
        oof_predictions,
        [
            "problem_id",
            "label_family_id",
            "label_cohort",
            "predicted_dp_probability",
            "predicted_family_id",
            "decision_threshold",
            "model_correct",
        ],
    )

    selection_summary_path.write_text(
        json.dumps(selection_summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "model_json": model_path,
        "feature_weights_csv": feature_weights_path,
        "oof_predictions_csv": oof_predictions_path,
        "selection_summary_json": selection_summary_path,
    }


def train_selector_prior_v2_pipeline(
    *,
    input_csv: Path,
    output_dir: Path,
    prefix: str,
    positive_class_weights: tuple[float, ...] = DEFAULT_POSITIVE_CLASS_WEIGHTS,
    objective_text_vocab_caps: tuple[int, ...] = DEFAULT_OBJECTIVE_TEXT_VOCAB_CAPS,
    threshold_grid: tuple[float, ...] = DEFAULT_THRESHOLD_GRID,
) -> dict[str, Any]:
    trusted_rows = load_selector_prior_rows(input_csv)
    curated_rows = build_curated_training_rows(trusted_rows)
    selection = select_selector_prior_v2_configuration(
        curated_rows,
        positive_class_weights=positive_class_weights,
        objective_text_vocab_caps=objective_text_vocab_caps,
        threshold_grid=threshold_grid,
    )
    training_metadata = _build_training_metadata(
        input_csv=input_csv,
        rows=curated_rows,
        cohort_priority=("selected_family", "rerun", "unknown"),
        eval_protocol="leave_one_problem_out",
    )
    selection_metadata = {
        "chosen_positive_class_weight": selection["chosen_positive_class_weight"],
        "chosen_threshold": selection["chosen_threshold"],
        "chosen_feature_switches": asdict(selection["chosen_feature_switches"]),
        "weighted_label_family_id": WEIGHTED_LABEL_FAMILY_ID,
        "success_criteria": dict(DEFAULT_SUCCESS_CRITERIA),
        "single_example_balanced_accuracy_swing_threshold": selection["selection_summary"][
            "single_example_balanced_accuracy_swing_threshold"
        ],
        "selection_protocol": dict(selection["selection_summary"]["selection_protocol"]),
    }
    model = fit_selector_prior_v2(
        curated_rows,
        positive_class_weight=selection["chosen_positive_class_weight"],
        feature_switches=selection["chosen_feature_switches"],
        decision_threshold=selection["chosen_threshold"],
        training_metadata=training_metadata,
        selection_metadata=selection_metadata,
    )
    artifacts = write_selector_prior_v2_training_artifacts(
        model=model,
        selection_summary=selection["selection_summary"],
        oof_predictions=selection["oof_predictions"],
        output_dir=output_dir,
        prefix=prefix,
    )
    return {
        "rows": curated_rows,
        "selection_summary": selection["selection_summary"],
        "oof_predictions": selection["oof_predictions"],
        "model": model,
        "artifacts": artifacts,
    }


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> dict[str, float]:
    if total <= 0:
        return {"lower": 0.0, "upper": 0.0}
    phat = successes / total
    denominator = 1.0 + (z**2) / total
    center = (phat + (z**2) / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt((phat * (1.0 - phat) + (z**2) / (4.0 * total)) / total)
        / denominator
    )
    return {"lower": max(0.0, center - margin), "upper": min(1.0, center + margin)}


def _discordant_counts(actual_labels: list[str], v2_predictions: list[str], baseline_predictions: list[str]) -> dict[str, int]:
    v2_only_correct = 0
    baseline_only_correct = 0
    both_correct = 0
    both_wrong = 0
    for actual_label, v2_prediction, baseline_prediction in zip(actual_labels, v2_predictions, baseline_predictions):
        v2_correct = v2_prediction == actual_label
        baseline_correct = baseline_prediction == actual_label
        if v2_correct and baseline_correct:
            both_correct += 1
        elif v2_correct and not baseline_correct:
            v2_only_correct += 1
        elif baseline_correct and not v2_correct:
            baseline_only_correct += 1
        else:
            both_wrong += 1
    return {
        "v2_only_correct": v2_only_correct,
        "baseline_only_correct": baseline_only_correct,
        "both_correct": both_correct,
        "both_wrong": both_wrong,
    }


def _derive_holdout_key(path: Path) -> str:
    match = re.search(r"(batch[0-9]+)", path.stem)
    if match:
        return match.group(1)
    return path.stem


def _comparison_provenance(
    *,
    canonical_v1_model_json: Path,
    canonical_v1_dev_trusted_csv: Path,
) -> dict[str, Any]:
    v1_payload = json.loads(canonical_v1_model_json.read_text(encoding="utf-8"))
    return {
        "always_primary": {"source_kind": "same_row_current_holdout_rule"},
        "always_enumeration": {"source_kind": "same_row_current_holdout_rule"},
        "always_dp": {"source_kind": "same_row_current_holdout_rule"},
        "rule_has_math": {"source_kind": "same_row_current_holdout_rule"},
        "rule_small_math_pattern": {"source_kind": "same_row_current_holdout_rule"},
        "prior_v1_logistic": {
            "source_kind": "canonical_v1_model",
            "model_json_path": str(canonical_v1_model_json.resolve()),
            "dev_trusted_csv_path": str(canonical_v1_dev_trusted_csv.resolve()),
            "training_metadata": dict(v1_payload.get("training_metadata") or {}),
        },
    }


def _judge_success(
    *,
    v2_metrics: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
    swing_threshold: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if v2_metrics["balanced_accuracy"] <= baseline_metrics["always_dp"]["balanced_accuracy"]:
        reasons.append("balanced_accuracy_not_above_always_dp")
    if v2_metrics["balanced_accuracy"] <= baseline_metrics["rule_has_math"]["balanced_accuracy"]:
        reasons.append("balanced_accuracy_not_above_rule_has_math")
    if v2_metrics["accuracy"] < baseline_metrics["always_dp"]["accuracy"] + DEFAULT_SUCCESS_CRITERIA["min_accuracy_delta_vs_always_dp"]:
        reasons.append("accuracy_below_guardrail")
    if v2_metrics["dp_recall"] < DEFAULT_SUCCESS_CRITERIA["min_dp_recall"]:
        reasons.append("dp_recall_below_guardrail")
    if reasons:
        return "fail", reasons

    delta_vs_always_dp = v2_metrics["balanced_accuracy"] - baseline_metrics["always_dp"]["balanced_accuracy"]
    delta_vs_rule_has_math = v2_metrics["balanced_accuracy"] - baseline_metrics["rule_has_math"]["balanced_accuracy"]
    if delta_vs_always_dp <= swing_threshold or delta_vs_rule_has_math <= swing_threshold:
        return "inconclusive", ["balanced_accuracy_gain_within_single_example_swing"]
    return "success", []


def summarize_selector_prior_v2_prediction_rows(
    prediction_rows: list[dict[str, Any]],
    *,
    evaluation_kind: str,
    chosen_positive_class_weight: float,
    chosen_threshold: float,
    chosen_feature_switches: dict[str, Any],
    comparison_baselines: dict[str, Any],
) -> dict[str, Any]:
    sorted_rows = sorted(prediction_rows, key=lambda row: str(row["problem_id"]))
    seen_problem_ids: set[str] = set()
    for row in sorted_rows:
        problem_id = str(row["problem_id"])
        if problem_id in seen_problem_ids:
            raise ValueError(f"duplicate problem_id in selector prior v2 predictions: {problem_id}")
        seen_problem_ids.add(problem_id)

    actual_labels = [str(row["label_family_id"]) for row in sorted_rows]
    prediction_columns = {
        "v2": "v2_prediction",
        "prior_v1_logistic": "prior_v1_logistic_prediction",
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
        for baseline_name, prediction_column in prediction_columns.items()
    }
    v2_metrics = baseline_metrics["v2"]
    num_dp = sum(1 for label in actual_labels if label == DP_FAMILY_ID)
    num_enumeration = sum(1 for label in actual_labels if label == ENUMERATION_FAMILY_ID)
    swing_threshold = _single_example_balanced_accuracy_swing_threshold(actual_labels)
    success_judgment, judgment_reasons = _judge_success(
        v2_metrics=v2_metrics,
        baseline_metrics=baseline_metrics,
        swing_threshold=swing_threshold,
    )

    summary = {
        "evaluation_kind": evaluation_kind,
        "weighted_label_family_id": WEIGHTED_LABEL_FAMILY_ID,
        "chosen_positive_class_weight": float(chosen_positive_class_weight),
        "chosen_threshold": float(chosen_threshold),
        "frozen_threshold": float(chosen_threshold),
        "chosen_feature_switches": dict(chosen_feature_switches),
        "num_examples": len(sorted_rows),
        "num_unique_problem_ids": len(seen_problem_ids),
        "label_distribution": dict(Counter(actual_labels)),
        "accuracy": v2_metrics["accuracy"],
        "balanced_accuracy": v2_metrics["balanced_accuracy"],
        "dp_recall": v2_metrics["dp_recall"],
        "enumeration_recall": v2_metrics["enumeration_recall"],
        "confusion_matrix": v2_metrics["confusion_matrix"],
        "accuracy_wilson_interval": _wilson_interval(
            sum(1 for row in sorted_rows if row["v2_prediction"] == row["label_family_id"]),
            len(sorted_rows),
        ),
        "dp_recall_wilson_interval": _wilson_interval(
            int(v2_metrics["confusion_matrix"][DP_FAMILY_ID][DP_FAMILY_ID]),
            num_dp,
        ),
        "enumeration_recall_wilson_interval": _wilson_interval(
            int(v2_metrics["confusion_matrix"][ENUMERATION_FAMILY_ID][ENUMERATION_FAMILY_ID]),
            num_enumeration,
        ),
        "baseline_metrics": baseline_metrics,
        "balanced_accuracy_delta_vs_always_dp": (
            v2_metrics["balanced_accuracy"] - baseline_metrics["always_dp"]["balanced_accuracy"]
        ),
        "balanced_accuracy_delta_vs_rule_has_math": (
            v2_metrics["balanced_accuracy"] - baseline_metrics["rule_has_math"]["balanced_accuracy"]
        ),
        "balanced_accuracy_delta_vs_rule_small_math_pattern": (
            v2_metrics["balanced_accuracy"] - baseline_metrics["rule_small_math_pattern"]["balanced_accuracy"]
        ),
        "balanced_accuracy_delta_vs_prior_v1_logistic": (
            v2_metrics["balanced_accuracy"] - baseline_metrics["prior_v1_logistic"]["balanced_accuracy"]
        ),
        "discordant_counts": {
            baseline_name: _discordant_counts(
                actual_labels,
                [str(row["v2_prediction"]) for row in sorted_rows],
                [str(row[prediction_column]) for row in sorted_rows],
            )
            for baseline_name, prediction_column in prediction_columns.items()
            if baseline_name != "v2"
        },
        "comparison_baselines": comparison_baselines,
        "success_criteria": {
            **DEFAULT_SUCCESS_CRITERIA,
            "judgment_states": ["success", "fail", "inconclusive"],
        },
        "single_example_balanced_accuracy_swing_threshold": swing_threshold,
        "success_judgment": success_judgment,
        "judgment_reasons": judgment_reasons,
    }
    return {
        "summary": summary,
        "predictions": sorted_rows,
    }


def evaluate_selector_prior_v2_external_holdout(
    *,
    dev_trusted_csv: Path,
    holdout_trusted_csv: Path,
    v2_model_json: Path,
    canonical_v1_dev_trusted_csv: Path,
    canonical_v1_model_json: Path,
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
        model_json_path=v2_model_json,
    )
    canonical_v1_dev_rows = build_curated_training_rows(load_selector_prior_rows(canonical_v1_dev_trusted_csv))
    _validate_model_provenance(
        dev_trusted_csv=canonical_v1_dev_trusted_csv,
        dev_rows=canonical_v1_dev_rows,
        model_json_path=canonical_v1_model_json,
    )
    canonical_v1_dev_problem_ids = sorted({row.problem_id for row in canonical_v1_dev_rows})
    if dev_problem_ids != canonical_v1_dev_problem_ids:
        raise ValueError("dev cohort mismatch between v2 dev_trusted_csv and canonical_v1_dev_trusted_csv")

    v2_model = load_selector_prior_v2_model(v2_model_json)
    canonical_v1_model = load_selector_prior_model(canonical_v1_model_json)
    v2_predictions = {prediction.problem_id: prediction for prediction in predict_selector_prior_v2(v2_model, holdout_rows)}
    v1_predictions = {prediction.problem_id: prediction for prediction in predict_selector_prior(canonical_v1_model, holdout_rows)}

    prediction_rows: list[dict[str, Any]] = []
    for row in sorted(holdout_rows, key=lambda item: item.problem_id):
        v2_prediction = v2_predictions[row.problem_id]
        v1_prediction = v1_predictions[row.problem_id]
        rule_has_math_prediction = predict_rule_has_math(row)
        rule_small_math_pattern_prediction = predict_rule_small_math_pattern(row)
        always_primary_prediction = row.primary_family_id
        always_enumeration_prediction = ENUMERATION_FAMILY_ID
        always_dp_prediction = DP_FAMILY_ID

        prediction_rows.append(
            {
                "problem_id": row.problem_id,
                "label_family_id": row.label_family_id,
                "label_cohort": row.label_cohort,
                "canonical_tags_joined": row.raw_features["canonical_tags_joined"],
                "problem_tags_joined": row.raw_features["problem_tags_joined"],
                "v2_prediction": v2_prediction.predicted_family_id,
                "v2_correct": v2_prediction.model_correct,
                "v2_predicted_dp_probability": v2_prediction.predicted_dp_probability,
                "prior_v1_logistic_prediction": v1_prediction.predicted_family_id,
                "prior_v1_logistic_correct": v1_prediction.model_correct,
                "prior_v1_logistic_predicted_dp_probability": v1_prediction.predicted_dp_probability,
                "always_primary_prediction": always_primary_prediction,
                "always_primary_correct": int(always_primary_prediction == row.label_family_id),
                "always_enumeration_prediction": always_enumeration_prediction,
                "always_enumeration_correct": int(always_enumeration_prediction == row.label_family_id),
                "always_dp_prediction": always_dp_prediction,
                "always_dp_correct": int(always_dp_prediction == row.label_family_id),
                "rule_has_math_prediction": rule_has_math_prediction,
                "rule_has_math_correct": int(rule_has_math_prediction == row.label_family_id),
                "rule_small_math_pattern_prediction": rule_small_math_pattern_prediction,
                "rule_small_math_pattern_correct": int(
                    rule_small_math_pattern_prediction == row.label_family_id
                ),
            }
        )

    comparison_baselines = _comparison_provenance(
        canonical_v1_model_json=canonical_v1_model_json,
        canonical_v1_dev_trusted_csv=canonical_v1_dev_trusted_csv,
    )
    evaluation = summarize_selector_prior_v2_prediction_rows(
        prediction_rows,
        evaluation_kind=f"external_holdout_{_derive_holdout_key(holdout_trusted_csv)}",
        chosen_positive_class_weight=float(v2_model.positive_class_weight),
        chosen_threshold=float(v2_model.decision_threshold),
        chosen_feature_switches=asdict(v2_model.feature_switches),
        comparison_baselines=comparison_baselines,
    )
    evaluation["summary"].update(
        {
            "dev_num_examples": len(dev_rows),
            "dev_num_unique_problem_ids": len(dev_problem_ids),
            "dev_holdout_overlap_count": len(overlap_problem_ids),
            "dev_holdout_overlap_problem_ids": overlap_problem_ids,
        }
    )
    return evaluation


def write_selector_prior_v2_holdout_artifacts(
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
        "v2_prediction",
        "v2_correct",
        "v2_predicted_dp_probability",
        "prior_v1_logistic_prediction",
        "prior_v1_logistic_correct",
        "prior_v1_logistic_predicted_dp_probability",
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
    _write_csv(predictions_path, prediction_rows, fieldnames)
    return {"summary_json": summary_path, "predictions_csv": predictions_path}


def run_selector_prior_v2_holdout_pipeline(
    *,
    dev_trusted_csv: Path,
    v2_model_json: Path,
    holdout_trusted_csvs: list[Path],
    canonical_v1_dev_trusted_csv: Path,
    canonical_v1_model_json: Path,
    output_dir: Path,
    prefix: str,
) -> dict[str, Any]:
    holdout_results: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, Path] = {}
    cumulative_prediction_rows: list[dict[str, Any]] = []
    comparison_baselines = _comparison_provenance(
        canonical_v1_model_json=canonical_v1_model_json,
        canonical_v1_dev_trusted_csv=canonical_v1_dev_trusted_csv,
    )
    v2_model = load_selector_prior_v2_model(v2_model_json)

    for holdout_trusted_csv in holdout_trusted_csvs:
        holdout_key = _derive_holdout_key(holdout_trusted_csv)
        evaluation = evaluate_selector_prior_v2_external_holdout(
            dev_trusted_csv=dev_trusted_csv,
            holdout_trusted_csv=holdout_trusted_csv,
            v2_model_json=v2_model_json,
            canonical_v1_dev_trusted_csv=canonical_v1_dev_trusted_csv,
            canonical_v1_model_json=canonical_v1_model_json,
        )
        holdout_results[holdout_key] = evaluation
        cumulative_prediction_rows.extend(evaluation["predictions"])
        holdout_artifacts = write_selector_prior_v2_holdout_artifacts(
            evaluation=evaluation,
            output_dir=output_dir,
            prefix=f"{prefix}_holdout_{holdout_key}",
        )
        artifacts.update({f"{holdout_key}_{name}": path for name, path in holdout_artifacts.items()})

    cumulative_evaluation = summarize_selector_prior_v2_prediction_rows(
        cumulative_prediction_rows,
        evaluation_kind="external_holdout_cumulative",
        chosen_positive_class_weight=float(v2_model.positive_class_weight),
        chosen_threshold=float(v2_model.decision_threshold),
        chosen_feature_switches=asdict(v2_model.feature_switches),
        comparison_baselines=comparison_baselines,
    )
    cumulative_artifacts = write_selector_prior_v2_holdout_artifacts(
        evaluation=cumulative_evaluation,
        output_dir=output_dir,
        prefix=f"{prefix}_holdout_cumulative",
    )
    artifacts.update({f"cumulative_{name}": path for name, path in cumulative_artifacts.items()})
    return {
        "holdouts": holdout_results,
        "cumulative": cumulative_evaluation,
        "artifacts": artifacts,
    }
