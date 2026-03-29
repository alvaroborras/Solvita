from __future__ import annotations

import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


ONLINE_VISIBLE_SOURCE_FIELDS = ("description", "tags", "test_case")

RECIPE_DP_MEMO_DEFAULT = "recipe.dp.memo_default"
RECIPE_ENUM_SIMULATION_DEFAULT = "recipe.enum.simulation_default"
RECIPE_SPECIALIZED_OTHER = "recipe.specialized.other"

RECIPE_BUCKETS = (
    RECIPE_DP_MEMO_DEFAULT,
    RECIPE_ENUM_SIMULATION_DEFAULT,
    RECIPE_SPECIALIZED_OTHER,
)

TEMPLATE_BUCKET_RULES = {
    "Top-down Memoized DP": RECIPE_DP_MEMO_DEFAULT,
    "N-Nested Loops Simulation (Dynamic Depth DFS)": RECIPE_ENUM_SIMULATION_DEFAULT,
}

DEFAULT_SUCCESS_THRESHOLD = 0.5
DEFAULT_MIN_BUCKET_EXAMPLES = 5
DEFAULT_DESCRIPTION_VOCAB_CAP = 512
DEFAULT_DESCRIPTION_MIN_TOKEN_FREQUENCY = 1
DEFAULT_LEARNING_RATE = 0.1
DEFAULT_TRAINING_STEPS = 500
DEFAULT_L2 = 0.01
DEFAULT_RELIABILITY_BINS = 10
DEFAULT_MIN_MULTI_BUCKET_PROBLEMS = 25
DEFAULT_MIN_MULTI_BUCKET_FRACTION = 0.20

DESCRIPTION_STAT_NAMES = (
    "description_chars",
    "description_lines",
    "description_token_count",
    "description_digit_ratio",
)

TEST_CASE_STAT_NAMES = (
    "num_tests",
    "median_input_chars",
    "max_input_chars",
    "median_output_chars",
    "max_output_chars",
    "median_input_lines",
    "median_output_lines",
    "token_count_input",
    "token_count_output",
    "digit_ratio_input",
    "digit_ratio_output",
)

NUMERIC_FEATURE_NAMES = DESCRIPTION_STAT_NAMES + TEST_CASE_STAT_NAMES
TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class OracleMemoryFeatureConfig:
    description_vocab_cap: int = DEFAULT_DESCRIPTION_VOCAB_CAP
    description_min_token_frequency: int = DEFAULT_DESCRIPTION_MIN_TOKEN_FREQUENCY
    include_action_interactions: bool = True


@dataclass(frozen=True)
class OracleMemoryFeatureFrame:
    matrix: np.ndarray
    success_labels: np.ndarray
    fully_certified_labels: np.ndarray
    feature_names: tuple[str, ...]
    feature_vocab: dict[str, int]
    numeric_stats: dict[str, dict[str, float]]
    feature_config: OracleMemoryFeatureConfig


@dataclass(frozen=True)
class OracleMemoryPolicyModel:
    feature_names: tuple[str, ...]
    feature_vocab: dict[str, int]
    weights: np.ndarray
    numeric_stats: dict[str, dict[str, float]]
    feature_config: OracleMemoryFeatureConfig
    success_threshold: float
    learning_rate: float
    steps: int
    l2: float
    training_metadata: dict[str, Any] | None = None


def recipe_bucket_from_template_name(selected_template_name: str) -> str:
    template_name = str(selected_template_name or "").strip()
    if template_name in TEMPLATE_BUCKET_RULES:
        return TEMPLATE_BUCKET_RULES[template_name]
    return RECIPE_SPECIALIZED_OTHER


def _coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [part.strip() for part in text.split("|") if part.strip()]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()] if str(parsed).strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    visible_chars = [char for char in text if not char.isspace()]
    if not visible_chars:
        return 0.0
    digit_count = sum(1 for char in visible_chars if char.isdigit())
    return digit_count / len(visible_chars)


def tokenize_description(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(str(text or "").lower()) if len(token) >= 2]


def compute_description_statistics(description: str) -> dict[str, float]:
    text = str(description or "")
    return {
        "description_chars": len(text),
        "description_lines": len(text.splitlines()) if text else 0,
        "description_token_count": len(tokenize_description(text)),
        "description_digit_ratio": _digit_ratio(text),
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def _line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def compute_test_case_statistics(test_cases: list[dict[str, Any]]) -> dict[str, float]:
    normalized_cases = test_cases if isinstance(test_cases, list) else []
    input_chars: list[float] = []
    output_chars: list[float] = []
    input_lines: list[float] = []
    output_lines: list[float] = []
    token_count_input = 0
    token_count_output = 0
    all_inputs = []
    all_outputs = []

    for case in normalized_cases:
        input_text = str(case.get("input", "") or "")
        output_text = str(case.get("output", "") or "")
        all_inputs.append(input_text)
        all_outputs.append(output_text)
        input_chars.append(float(len(input_text)))
        output_chars.append(float(len(output_text)))
        input_lines.append(float(_line_count(input_text)))
        output_lines.append(float(_line_count(output_text)))
        token_count_input += len(TOKEN_RE.findall(input_text))
        token_count_output += len(TOKEN_RE.findall(output_text))

    return {
        "num_tests": len(normalized_cases),
        "median_input_chars": _median(input_chars),
        "max_input_chars": max(input_chars) if input_chars else 0.0,
        "median_output_chars": _median(output_chars),
        "max_output_chars": max(output_chars) if output_chars else 0.0,
        "median_input_lines": _median(input_lines),
        "median_output_lines": _median(output_lines),
        "token_count_input": token_count_input,
        "token_count_output": token_count_output,
        "digit_ratio_input": _digit_ratio("".join(all_inputs)),
        "digit_ratio_output": _digit_ratio("".join(all_outputs)),
    }


def _load_problem_source_rows(source_jsonl: Path, required_problem_ids: set[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    with source_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            problem_id = str(row.get("id") or row.get("problem_id") or "")
            if not problem_id or problem_id not in required_problem_ids:
                continue
            index[problem_id] = dict(row)
    return index


def load_audit_csv_rows(audit_csv_paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in audit_csv_paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows.extend(dict(row) for row in reader if str(row.get("problem_id") or "").strip())
    return rows


def _visible_context_from_problem_row(problem_row: dict[str, Any]) -> dict[str, Any]:
    description = str(problem_row.get("description") or "")
    tags = _coerce_tags(problem_row.get("tags"))
    test_cases = problem_row.get("test_case")
    test_cases = test_cases if isinstance(test_cases, list) else []
    return {
        "problem_id": str(problem_row.get("id") or problem_row.get("problem_id") or ""),
        "description": description,
        "tags": tags,
        "test_case_stats": compute_test_case_statistics(test_cases),
    }


def build_training_examples(
    *,
    audit_rows: list[dict[str, str]],
    source_jsonl: Path,
) -> list[dict[str, Any]]:
    required_problem_ids = {
        str(row.get("problem_id") or "").strip()
        for row in audit_rows
        if str(row.get("problem_id") or "").strip()
    }
    source_index = _load_problem_source_rows(source_jsonl, required_problem_ids)
    missing_problem_ids = sorted(problem_id for problem_id in required_problem_ids if problem_id not in source_index)
    if missing_problem_ids:
        raise ValueError(f"missing source rows for {len(missing_problem_ids)} problem_ids: {', '.join(missing_problem_ids[:10])}")

    examples: list[dict[str, Any]] = []
    for row in audit_rows:
        problem_id = str(row.get("problem_id") or "").strip()
        if not problem_id:
            continue
        visible_context = _visible_context_from_problem_row(source_index[problem_id])
        description = visible_context["description"]
        tags = list(visible_context["tags"])
        test_case_stats = dict(visible_context["test_case_stats"])
        description_stats = compute_description_statistics(description)
        selected_template_name = str(row.get("selected_template_name") or "").strip()
        examples.append(
            {
                "problem_id": problem_id,
                "source_path": str(row.get("source_path") or ""),
                "selected_template_name": selected_template_name,
                "recipe_bucket": recipe_bucket_from_template_name(selected_template_name),
                "decision": str(row.get("decision") or ""),
                "reward_reason": str(row.get("reward_reason") or ""),
                "is_success": int(str(row.get("decision") or "") == "accept"),
                "is_fully_certified": int(str(row.get("reward_reason") or "") == "fully_certified"),
                "description": description,
                "tags": tags,
                "description_stats": description_stats,
                "test_case_stats": test_case_stats,
                "visible_context": visible_context,
            }
        )
    return examples


def summarize_recipe_bucket_support(
    audit_rows: list[dict[str, str]],
    *,
    min_bucket_examples: int = DEFAULT_MIN_BUCKET_EXAMPLES,
) -> dict[str, Any]:
    template_counts = Counter()
    bucket_counts = Counter()
    decision_counts = Counter()
    fully_certified_counts = Counter()
    by_problem_id: dict[str, set[str]] = defaultdict(set)
    bucket_mapping: dict[str, str] = {}

    for row in audit_rows:
        problem_id = str(row.get("problem_id") or "").strip()
        template_name = str(row.get("selected_template_name") or "").strip()
        bucket_name = recipe_bucket_from_template_name(template_name)
        bucket_counts[bucket_name] += 1
        if template_name:
            template_counts[template_name] += 1
            bucket_mapping[template_name] = bucket_name
        if problem_id:
            by_problem_id[problem_id].add(bucket_name)
        decision_key = "accept" if str(row.get("decision") or "") == "accept" else "reject"
        decision_counts[(bucket_name, decision_key)] += 1
        fully_key = "fully_certified" if str(row.get("reward_reason") or "") == "fully_certified" else "not_fully_certified"
        fully_certified_counts[(bucket_name, fully_key)] += 1

    coverage_hist = Counter(len(bucket_names) for bucket_names in by_problem_id.values())
    support_gate_passed = all(bucket_counts.get(bucket_name, 0) >= min_bucket_examples for bucket_name in RECIPE_BUCKETS)

    return {
        "total_rows": len(audit_rows),
        "unique_problem_ids": len(by_problem_id),
        "unique_templates": len(template_counts),
        "template_counts": dict(template_counts.most_common()),
        "bucket_mapping": bucket_mapping,
        "bucket_counts": {bucket_name: bucket_counts.get(bucket_name, 0) for bucket_name in RECIPE_BUCKETS},
        "decision_counts": {
            bucket_name: {
                "accept": decision_counts.get((bucket_name, "accept"), 0),
                "reject": decision_counts.get((bucket_name, "reject"), 0),
            }
            for bucket_name in RECIPE_BUCKETS
        },
        "fully_certified_counts": {
            bucket_name: {
                "fully_certified": fully_certified_counts.get((bucket_name, "fully_certified"), 0),
                "not_fully_certified": fully_certified_counts.get((bucket_name, "not_fully_certified"), 0),
            }
            for bucket_name in RECIPE_BUCKETS
        },
        "problem_bucket_coverage_histogram": dict(sorted(coverage_hist.items())),
        "multi_bucket_problem_count": sum(1 for buckets in by_problem_id.values() if len(buckets) >= 2),
        "max_observed_buckets_per_problem": max((len(buckets) for buckets in by_problem_id.values()), default=0),
        "min_bucket_examples": int(min_bucket_examples),
        "support_gate_passed": support_gate_passed,
    }


def _numeric_value(example: dict[str, Any], feature_name: str) -> float:
    if feature_name in DESCRIPTION_STAT_NAMES:
        return float(example["description_stats"].get(feature_name, 0.0))
    return float(example["test_case_stats"].get(feature_name, 0.0))


def _compute_numeric_stats(examples: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for feature_name in NUMERIC_FEATURE_NAMES:
        raw_values = np.array([math.log1p(max(_numeric_value(example, feature_name), 0.0)) for example in examples], dtype=np.float64)
        mean = float(raw_values.mean()) if len(raw_values) else 0.0
        std = float(raw_values.std()) if len(raw_values) else 1.0
        if std <= 1e-9:
            std = 1.0
        stats[feature_name] = {"mean": mean, "std": std}
    return stats


def _fit_description_vocabulary(
    examples: list[dict[str, Any]],
    *,
    config: OracleMemoryFeatureConfig,
) -> tuple[str, ...]:
    counter: Counter[str] = Counter()
    for example in examples:
        counter.update(set(tokenize_description(example["description"])))
    ranked = [
        token
        for token, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if count >= config.description_min_token_frequency
    ]
    return tuple(ranked[: config.description_vocab_cap])


def _example_feature_map(
    example: dict[str, Any],
    *,
    numeric_stats: dict[str, dict[str, float]],
    config: OracleMemoryFeatureConfig,
    description_vocabulary: tuple[str, ...],
) -> dict[str, float]:
    feature_map: dict[str, float] = {"bias": 1.0}
    recipe_bucket = str(example["recipe_bucket"])
    feature_map[f"bucket::{recipe_bucket}"] = 1.0

    for tag in sorted(set(example["tags"])):
        feature_map[f"tag::{tag}"] = 1.0

    allowed_description_tokens = set(description_vocabulary)
    for token in sorted(set(tokenize_description(example["description"]))):
        if token in allowed_description_tokens:
            feature_map[f"description_token::{token}"] = 1.0

    for feature_name in NUMERIC_FEATURE_NAMES:
        transformed_value = math.log1p(max(_numeric_value(example, feature_name), 0.0))
        stats = numeric_stats[feature_name]
        feature_map[f"numeric::{feature_name}"] = (transformed_value - stats["mean"]) / stats["std"]

    if config.include_action_interactions:
        base_items = list(feature_map.items())
        for feature_name, feature_value in base_items:
            if feature_name == "bias" or feature_name.startswith("bucket::"):
                continue
            feature_map[f"action::{recipe_bucket}::{feature_name}"] = feature_value

    return feature_map


def build_feature_frame(
    examples: list[dict[str, Any]],
    *,
    feature_config: OracleMemoryFeatureConfig | None = None,
    fitted_vocab: dict[str, int] | None = None,
    numeric_stats: dict[str, dict[str, float]] | None = None,
    description_vocabulary: tuple[str, ...] | None = None,
) -> OracleMemoryFeatureFrame:
    feature_config = feature_config or OracleMemoryFeatureConfig()
    if numeric_stats is None:
        numeric_stats = _compute_numeric_stats(examples)
    if description_vocabulary is None:
        description_vocabulary = _fit_description_vocabulary(examples, config=feature_config)

    row_feature_maps = [
        _example_feature_map(
            example,
            numeric_stats=numeric_stats,
            config=feature_config,
            description_vocabulary=description_vocabulary,
        )
        for example in examples
    ]

    if fitted_vocab is None:
        feature_names = tuple(sorted({feature_name for feature_map in row_feature_maps for feature_name in feature_map}))
        feature_vocab = {feature_name: index for index, feature_name in enumerate(feature_names)}
    else:
        feature_vocab = dict(fitted_vocab)
        feature_names = tuple(name for name, _ in sorted(feature_vocab.items(), key=lambda item: item[1]))

    matrix = np.zeros((len(examples), len(feature_vocab)), dtype=np.float64)
    for row_index, feature_map in enumerate(row_feature_maps):
        for feature_name, feature_value in feature_map.items():
            feature_index = feature_vocab.get(feature_name)
            if feature_index is None:
                continue
            matrix[row_index, feature_index] = feature_value

    success_labels = np.array([int(example["is_success"]) for example in examples], dtype=np.float64)
    fully_certified_labels = np.array([int(example["is_fully_certified"]) for example in examples], dtype=np.float64)
    return OracleMemoryFeatureFrame(
        matrix=matrix,
        success_labels=success_labels,
        fully_certified_labels=fully_certified_labels,
        feature_names=feature_names,
        feature_vocab=feature_vocab,
        numeric_stats=numeric_stats,
        feature_config=feature_config,
    )


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def _fit_binary_logreg(
    X: np.ndarray,
    y: np.ndarray,
    *,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    steps: int = DEFAULT_TRAINING_STEPS,
    l2: float = DEFAULT_L2,
) -> np.ndarray:
    if len(y) == 0:
        return np.zeros(X.shape[1], dtype=np.float64)
    if np.all(y == y[0]):
        weights = np.zeros(X.shape[1], dtype=np.float64)
        if X.shape[1] > 0:
            prior = float(np.clip(y[0], 1e-6, 1.0 - 1e-6))
            weights[0] = math.log(prior / (1.0 - prior))
        return weights

    weights = np.zeros(X.shape[1], dtype=np.float64)
    bias_index = 0 if X.shape[1] > 0 else None
    for _ in range(steps):
        probs = _sigmoid(X @ weights)
        gradient = (X.T @ (probs - y)) / max(len(y), 1)
        regularization = l2 * weights
        if bias_index is not None:
            regularization[bias_index] = 0.0
        gradient += regularization
        weights -= learning_rate * gradient
    return weights


def fit_oracle_memory_policy(
    examples: list[dict[str, Any]],
    *,
    feature_config: OracleMemoryFeatureConfig | None = None,
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    steps: int = DEFAULT_TRAINING_STEPS,
    l2: float = DEFAULT_L2,
    training_metadata: dict[str, Any] | None = None,
) -> OracleMemoryPolicyModel:
    if not examples:
        raise ValueError("cannot fit oracle memory policy with zero examples")
    frame = build_feature_frame(examples, feature_config=feature_config)
    weights = _fit_binary_logreg(
        frame.matrix,
        frame.success_labels,
        learning_rate=learning_rate,
        steps=steps,
        l2=l2,
    )
    return OracleMemoryPolicyModel(
        feature_names=frame.feature_names,
        feature_vocab=frame.feature_vocab,
        weights=weights,
        numeric_stats=frame.numeric_stats,
        feature_config=frame.feature_config,
        success_threshold=float(success_threshold),
        learning_rate=float(learning_rate),
        steps=int(steps),
        l2=float(l2),
        training_metadata=training_metadata,
    )


def predict_oracle_memory_policy(
    model: OracleMemoryPolicyModel,
    examples: list[dict[str, Any]],
) -> list[float]:
    if not examples:
        return []
    frame = build_feature_frame(
        examples,
        feature_config=model.feature_config,
        fitted_vocab=model.feature_vocab,
        numeric_stats=model.numeric_stats,
    )
    probabilities = _sigmoid(frame.matrix @ model.weights)
    return [float(probability) for probability in probabilities]


def _positive_rate(labels: list[int]) -> float:
    if not labels:
        return 0.0
    return sum(labels) / len(labels)


def _roc_auc(labels: list[int], probabilities: list[float]) -> float | None:
    positives = [prob for label, prob in zip(labels, probabilities) if label == 1]
    negatives = [prob for label, prob in zip(labels, probabilities) if label == 0]
    if not positives or not negatives:
        return None
    total_pairs = len(positives) * len(negatives)
    concordant = 0.0
    for positive_score in positives:
        for negative_score in negatives:
            if positive_score > negative_score:
                concordant += 1.0
            elif positive_score == negative_score:
                concordant += 0.5
    return concordant / total_pairs


def _reliability_bins(
    labels: list[int],
    probabilities: list[float],
    *,
    num_bins: int = DEFAULT_RELIABILITY_BINS,
) -> tuple[list[dict[str, Any]], float]:
    if not probabilities:
        return [], 0.0
    bins: list[dict[str, Any]] = []
    total = len(probabilities)
    ece = 0.0
    for index in range(num_bins):
        lower = index / num_bins
        upper = (index + 1) / num_bins
        members = [
            (label, probability)
            for label, probability in zip(labels, probabilities)
            if lower <= probability < upper or (index == num_bins - 1 and probability == 1.0)
        ]
        if not members:
            bins.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": 0,
                    "avg_probability": 0.0,
                    "empirical_rate": 0.0,
                }
            )
            continue
        avg_probability = sum(probability for _, probability in members) / len(members)
        empirical_rate = sum(label for label, _ in members) / len(members)
        ece += (len(members) / total) * abs(avg_probability - empirical_rate)
        bins.append(
            {
                "lower": lower,
                "upper": upper,
                "count": len(members),
                "avg_probability": avg_probability,
                "empirical_rate": empirical_rate,
            }
        )
    return bins, ece


def compute_probability_metrics(
    labels: list[int],
    probabilities: list[float],
    *,
    threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    num_bins: int = DEFAULT_RELIABILITY_BINS,
) -> dict[str, Any]:
    predicted = [int(probability >= threshold) for probability in probabilities]
    tp = sum(1 for label, pred in zip(labels, predicted) if label == 1 and pred == 1)
    tn = sum(1 for label, pred in zip(labels, predicted) if label == 0 and pred == 0)
    fp = sum(1 for label, pred in zip(labels, predicted) if label == 0 and pred == 1)
    fn = sum(1 for label, pred in zip(labels, predicted) if label == 1 and pred == 0)
    reliability_bins, ece = _reliability_bins(labels, probabilities, num_bins=num_bins)
    brier_score = (
        sum((probability - label) ** 2 for label, probability in zip(labels, probabilities)) / len(labels)
        if labels
        else 0.0
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "threshold": float(threshold),
        "num_examples": len(labels),
        "positive_rate": _positive_rate(labels),
        "accuracy": ((tp + tn) / len(labels)) if labels else 0.0,
        "auc": _roc_auc(labels, probabilities),
        "brier_score": brier_score,
        "precision": precision,
        "recall": recall,
        "confusion_matrix": {
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
        },
        "reliability_bins": reliability_bins,
        "ece": ece,
    }


def compute_group_oof_predictions(
    examples: list[dict[str, Any]],
    *,
    feature_config: OracleMemoryFeatureConfig | None = None,
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    steps: int = DEFAULT_TRAINING_STEPS,
    l2: float = DEFAULT_L2,
) -> list[dict[str, Any]]:
    by_problem_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        by_problem_id[str(example["problem_id"])].append(example)

    oof_rows: list[dict[str, Any]] = []
    for problem_id in sorted(by_problem_id):
        holdout_examples = by_problem_id[problem_id]
        train_examples = [
            example
            for other_problem_id, grouped_examples in by_problem_id.items()
            if other_problem_id != problem_id
            for example in grouped_examples
        ]
        if not train_examples:
            base_rate = _positive_rate([int(example["is_success"]) for example in holdout_examples])
            probabilities = [base_rate for _ in holdout_examples]
        else:
            model = fit_oracle_memory_policy(
                train_examples,
                feature_config=feature_config,
                success_threshold=success_threshold,
                learning_rate=learning_rate,
                steps=steps,
                l2=l2,
            )
            probabilities = predict_oracle_memory_policy(model, holdout_examples)

        for example, probability in zip(holdout_examples, probabilities):
            oof_rows.append(
                {
                    "problem_id": example["problem_id"],
                    "recipe_bucket": example["recipe_bucket"],
                    "selected_template_name": example["selected_template_name"],
                    "decision": example["decision"],
                    "reward_reason": example["reward_reason"],
                    "is_success": int(example["is_success"]),
                    "is_fully_certified": int(example["is_fully_certified"]),
                    "predicted_success_probability": float(probability),
                    "predicted_success_label": int(probability >= success_threshold),
                }
            )
    return sorted(oof_rows, key=lambda row: (str(row["problem_id"]), str(row["recipe_bucket"]), str(row["selected_template_name"])))


def analyze_recipe_ranking(
    prediction_rows: list[dict[str, Any]],
    *,
    min_multi_bucket_problems: int = DEFAULT_MIN_MULTI_BUCKET_PROBLEMS,
    min_multi_bucket_fraction: float = DEFAULT_MIN_MULTI_BUCKET_FRACTION,
) -> dict[str, Any]:
    by_problem_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prediction_rows:
        by_problem_id[str(row["problem_id"])].append(row)

    problem_bucket_sets = {problem_id: {str(row["recipe_bucket"]) for row in rows} for problem_id, rows in by_problem_id.items()}
    multi_bucket_problem_ids = sorted(problem_id for problem_id, buckets in problem_bucket_sets.items() if len(buckets) >= 2)
    multi_bucket_problem_count = len(multi_bucket_problem_ids)
    unique_problem_count = len(by_problem_id)
    multi_bucket_fraction = (multi_bucket_problem_count / unique_problem_count) if unique_problem_count else 0.0

    limitation_reasons: list[str] = []
    if multi_bucket_problem_count < min_multi_bucket_problems or multi_bucket_fraction < min_multi_bucket_fraction:
        limitation_reasons.append("insufficient_multi_bucket_problem_coverage")

    summary: dict[str, Any] = {
        "supported": len(limitation_reasons) == 0,
        "unique_problem_count": unique_problem_count,
        "multi_bucket_problem_count": multi_bucket_problem_count,
        "multi_bucket_problem_fraction": multi_bucket_fraction,
        "problem_bucket_coverage_histogram": dict(
            sorted(Counter(len(buckets) for buckets in problem_bucket_sets.values()).items())
        ),
        "limitation_reasons": limitation_reasons,
    }

    if limitation_reasons:
        return {"summary": summary, "problem_rankings": []}

    ranking_rows: list[dict[str, Any]] = []
    top1_success_rates: list[float] = []
    topk_hits: Counter[int] = Counter()
    eligible_problem_count = 0

    for problem_id in multi_bucket_problem_ids:
        grouped_by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in by_problem_id[problem_id]:
            grouped_by_bucket[str(row["recipe_bucket"])].append(row)

        per_bucket_rows: list[dict[str, Any]] = []
        for recipe_bucket, rows in grouped_by_bucket.items():
            avg_probability = sum(float(row["predicted_success_probability"]) for row in rows) / len(rows)
            observed_success_rate = sum(int(row["is_success"]) for row in rows) / len(rows)
            observed_full_rate = sum(int(row["is_fully_certified"]) for row in rows) / len(rows)
            per_bucket_rows.append(
                {
                    "problem_id": problem_id,
                    "recipe_bucket": recipe_bucket,
                    "predicted_success_probability": avg_probability,
                    "observed_success_rate": observed_success_rate,
                    "observed_fully_certified_rate": observed_full_rate,
                    "attempt_count": len(rows),
                }
            )

        per_bucket_rows.sort(key=lambda row: (-float(row["predicted_success_probability"]), row["recipe_bucket"]))
        ranking_rows.extend(
            {
                **row,
                "rank": rank,
            }
            for rank, row in enumerate(per_bucket_rows, start=1)
        )

        eligible_problem_count += 1
        top1_success_rates.append(float(per_bucket_rows[0]["observed_success_rate"]))
        successful_buckets = {row["recipe_bucket"] for row in per_bucket_rows if float(row["observed_success_rate"]) > 0.0}
        for k in (1, 2, 3):
            topk = {row["recipe_bucket"] for row in per_bucket_rows[:k]}
            if topk & successful_buckets:
                topk_hits[k] += 1

    summary.update(
        {
            "eligible_problem_count": eligible_problem_count,
            "top1_selected_recipe_historical_success_rate": (
                sum(top1_success_rates) / len(top1_success_rates) if top1_success_rates else 0.0
            ),
            "topk_coverage": {
                str(k): (topk_hits[k] / eligible_problem_count if eligible_problem_count else 0.0)
                for k in (1, 2, 3)
            },
        }
    )
    return {"summary": summary, "problem_rankings": ranking_rows}


def summarize_prediction_rows(
    prediction_rows: list[dict[str, Any]],
    *,
    success_threshold: float,
    ranking_min_multi_bucket_problems: int = DEFAULT_MIN_MULTI_BUCKET_PROBLEMS,
    ranking_min_multi_bucket_fraction: float = DEFAULT_MIN_MULTI_BUCKET_FRACTION,
) -> dict[str, Any]:
    success_labels = [int(row["is_success"]) for row in prediction_rows]
    fully_certified_labels = [int(row["is_fully_certified"]) for row in prediction_rows]
    probabilities = [float(row["predicted_success_probability"]) for row in prediction_rows]
    ranking = analyze_recipe_ranking(
        prediction_rows,
        min_multi_bucket_problems=ranking_min_multi_bucket_problems,
        min_multi_bucket_fraction=ranking_min_multi_bucket_fraction,
    )
    return {
        "observed_action_metrics": {
            "accept_prediction": compute_probability_metrics(
                success_labels,
                probabilities,
                threshold=success_threshold,
            ),
            "fully_certified_proxy": compute_probability_metrics(
                fully_certified_labels,
                probabilities,
                threshold=success_threshold,
            ),
        },
        "ranking_analysis": ranking["summary"],
        "problem_rankings": ranking["problem_rankings"],
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _flatten_training_example(example: dict[str, Any]) -> dict[str, Any]:
    flattened = {
        "problem_id": example["problem_id"],
        "source_path": example["source_path"],
        "selected_template_name": example["selected_template_name"],
        "recipe_bucket": example["recipe_bucket"],
        "decision": example["decision"],
        "reward_reason": example["reward_reason"],
        "is_success": int(example["is_success"]),
        "is_fully_certified": int(example["is_fully_certified"]),
        "description": example["description"],
        "tags_json": json.dumps(example["tags"], ensure_ascii=False),
    }
    for feature_name in DESCRIPTION_STAT_NAMES:
        flattened[feature_name] = example["description_stats"][feature_name]
    for feature_name in TEST_CASE_STAT_NAMES:
        flattened[feature_name] = example["test_case_stats"][feature_name]
    return flattened


def write_training_examples_csv(
    *,
    examples: list[dict[str, Any]],
    output_dir: Path,
    prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_training_examples.csv"
    rows = [_flatten_training_example(example) for example in examples]
    fieldnames = [
        "problem_id",
        "source_path",
        "selected_template_name",
        "recipe_bucket",
        "decision",
        "reward_reason",
        "is_success",
        "is_fully_certified",
        "description",
        "tags_json",
        *DESCRIPTION_STAT_NAMES,
        *TEST_CASE_STAT_NAMES,
    ]
    _write_csv(path, rows, fieldnames)
    return path


def load_training_examples_csv(training_examples_csv: Path) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    with training_examples_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            examples.append(
                {
                    "problem_id": str(row["problem_id"]),
                    "source_path": str(row.get("source_path") or ""),
                    "selected_template_name": str(row.get("selected_template_name") or ""),
                    "recipe_bucket": str(row["recipe_bucket"]),
                    "decision": str(row.get("decision") or ""),
                    "reward_reason": str(row.get("reward_reason") or ""),
                    "is_success": int(row["is_success"]),
                    "is_fully_certified": int(row["is_fully_certified"]),
                    "description": str(row.get("description") or ""),
                    "tags": _coerce_tags(row.get("tags_json") or "[]"),
                    "description_stats": {
                        feature_name: float(row.get(feature_name, 0.0) or 0.0)
                        for feature_name in DESCRIPTION_STAT_NAMES
                    },
                    "test_case_stats": {
                        feature_name: float(row.get(feature_name, 0.0) or 0.0)
                        for feature_name in TEST_CASE_STAT_NAMES
                    },
                    "visible_context": {
                        "problem_id": str(row["problem_id"]),
                        "description": str(row.get("description") or ""),
                        "tags": _coerce_tags(row.get("tags_json") or "[]"),
                        "test_case_stats": {
                            feature_name: float(row.get(feature_name, 0.0) or 0.0)
                            for feature_name in TEST_CASE_STAT_NAMES
                        },
                    },
                }
            )
    return examples


def write_model_json(
    *,
    model: OracleMemoryPolicyModel,
    output_dir: Path,
    prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_model.json"
    payload = serialize_oracle_memory_policy_model(model)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def serialize_oracle_memory_policy_model(model: OracleMemoryPolicyModel) -> dict[str, Any]:
    return {
        "feature_names": list(model.feature_names),
        "weights": [float(weight) for weight in model.weights.tolist()],
        "numeric_stats": model.numeric_stats,
        "feature_config": asdict(model.feature_config),
        "success_threshold": float(model.success_threshold),
        "learning_rate": float(model.learning_rate),
        "steps": int(model.steps),
        "l2": float(model.l2),
        "training_metadata": dict(model.training_metadata or {}),
        "online_visible_source_fields": list(ONLINE_VISIBLE_SOURCE_FIELDS),
        "recipe_buckets": list(RECIPE_BUCKETS),
        "template_bucket_rules": dict(TEMPLATE_BUCKET_RULES),
    }


def load_oracle_memory_policy_model_from_payload(payload: dict[str, Any]) -> OracleMemoryPolicyModel:
    feature_names = tuple(str(name) for name in payload["feature_names"])
    feature_vocab = {name: index for index, name in enumerate(feature_names)}
    return OracleMemoryPolicyModel(
        feature_names=feature_names,
        feature_vocab=feature_vocab,
        weights=np.array(payload["weights"], dtype=np.float64),
        numeric_stats={
            str(key): {"mean": float(value["mean"]), "std": float(value["std"])}
            for key, value in payload["numeric_stats"].items()
        },
        feature_config=OracleMemoryFeatureConfig(**payload.get("feature_config", {})),
        success_threshold=float(payload.get("success_threshold", DEFAULT_SUCCESS_THRESHOLD)),
        learning_rate=float(payload.get("learning_rate", DEFAULT_LEARNING_RATE)),
        steps=int(payload.get("steps", DEFAULT_TRAINING_STEPS)),
        l2=float(payload.get("l2", DEFAULT_L2)),
        training_metadata=dict(payload.get("training_metadata") or {}),
    )


def load_oracle_memory_policy_model(model_json: Path) -> OracleMemoryPolicyModel:
    payload = json.loads(model_json.read_text(encoding="utf-8"))
    return load_oracle_memory_policy_model_from_payload(payload)


def write_feature_weights_csv(
    *,
    model: OracleMemoryPolicyModel,
    output_dir: Path,
    prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_feature_weights.csv"
    rows = [
        {
            "feature_name": feature_name,
            "weight": float(weight),
            "abs_weight": abs(float(weight)),
        }
        for feature_name, weight in sorted(
            zip(model.feature_names, model.weights),
            key=lambda item: (-abs(float(item[1])), item[0]),
        )
    ]
    _write_csv(path, rows, ["feature_name", "weight", "abs_weight"])
    return path


def write_oof_predictions_csv(
    *,
    prediction_rows: list[dict[str, Any]],
    output_dir: Path,
    prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_oof_predictions.csv"
    fieldnames = [
        "problem_id",
        "recipe_bucket",
        "selected_template_name",
        "decision",
        "reward_reason",
        "is_success",
        "is_fully_certified",
        "predicted_success_probability",
        "predicted_success_label",
    ]
    _write_csv(path, prediction_rows, fieldnames)
    return path


def write_summary_json(
    *,
    summary: dict[str, Any],
    output_dir: Path,
    prefix: str,
    suffix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_{suffix}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_problem_rankings_csv(
    *,
    ranking_rows: list[dict[str, Any]],
    output_dir: Path,
    prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_problem_rankings.csv"
    fieldnames = [
        "problem_id",
        "rank",
        "recipe_bucket",
        "predicted_success_probability",
        "observed_success_rate",
        "observed_fully_certified_rate",
        "attempt_count",
    ]
    _write_csv(path, ranking_rows, fieldnames)
    return path


def train_oracle_memory_policy_pipeline(
    *,
    audit_csv_paths: list[Path],
    source_jsonl: Path,
    output_dir: Path,
    prefix: str,
    min_bucket_examples: int = DEFAULT_MIN_BUCKET_EXAMPLES,
    feature_config: OracleMemoryFeatureConfig | None = None,
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    steps: int = DEFAULT_TRAINING_STEPS,
    l2: float = DEFAULT_L2,
) -> dict[str, Any]:
    audit_rows = load_audit_csv_rows(audit_csv_paths)
    recipe_bucket_summary = summarize_recipe_bucket_support(audit_rows, min_bucket_examples=min_bucket_examples)
    if not recipe_bucket_summary["support_gate_passed"]:
        raise ValueError(
            "recipe bucket support too low for training: "
            + json.dumps(recipe_bucket_summary["bucket_counts"], ensure_ascii=False, sort_keys=True)
        )

    examples = build_training_examples(audit_rows=audit_rows, source_jsonl=source_jsonl)
    feature_config = feature_config or OracleMemoryFeatureConfig()
    oof_predictions = compute_group_oof_predictions(
        examples,
        feature_config=feature_config,
        success_threshold=success_threshold,
        learning_rate=learning_rate,
        steps=steps,
        l2=l2,
    )
    selection_summary = summarize_prediction_rows(
        oof_predictions,
        success_threshold=success_threshold,
    )
    selection_summary.update(
        {
            "selection_protocol": {
                "group_cv": "leave_one_problem_out",
                "success_threshold": float(success_threshold),
                "min_bucket_examples": int(min_bucket_examples),
                "description_vocab_cap": int(feature_config.description_vocab_cap),
                "description_min_token_frequency": int(feature_config.description_min_token_frequency),
                "include_action_interactions": bool(feature_config.include_action_interactions),
            },
            "recipe_bucket_summary_snapshot": {
                "bucket_counts": recipe_bucket_summary["bucket_counts"],
                "multi_bucket_problem_count": recipe_bucket_summary["multi_bucket_problem_count"],
                "problem_bucket_coverage_histogram": recipe_bucket_summary["problem_bucket_coverage_histogram"],
            },
        }
    )

    training_metadata = {
        "audit_csv_paths": [str(path.resolve()) for path in audit_csv_paths],
        "source_jsonl": str(source_jsonl.resolve()),
        "num_examples": len(examples),
        "num_unique_problem_ids": len({example["problem_id"] for example in examples}),
        "bucket_counts": dict(recipe_bucket_summary["bucket_counts"]),
    }
    model = fit_oracle_memory_policy(
        examples,
        feature_config=feature_config,
        success_threshold=success_threshold,
        learning_rate=learning_rate,
        steps=steps,
        l2=l2,
        training_metadata=training_metadata,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "recipe_bucket_summary_json": write_summary_json(
            summary=recipe_bucket_summary,
            output_dir=output_dir,
            prefix=prefix,
            suffix="recipe_bucket_summary",
        ),
        "training_examples_csv": write_training_examples_csv(examples=examples, output_dir=output_dir, prefix=prefix),
        "model_json": write_model_json(model=model, output_dir=output_dir, prefix=prefix),
        "feature_weights_csv": write_feature_weights_csv(model=model, output_dir=output_dir, prefix=prefix),
        "oof_predictions_csv": write_oof_predictions_csv(
            prediction_rows=oof_predictions,
            output_dir=output_dir,
            prefix=prefix,
        ),
        "selection_summary_json": write_summary_json(
            summary=selection_summary,
            output_dir=output_dir,
            prefix=prefix,
            suffix="selection_summary",
        ),
    }
    return {
        "audit_rows": audit_rows,
        "examples": examples,
        "recipe_bucket_summary": recipe_bucket_summary,
        "selection_summary": selection_summary,
        "oof_predictions": oof_predictions,
        "model": model,
        "artifacts": artifacts,
    }


def train_oracle_memory_policy_from_examples(
    examples: list[dict[str, Any]],
    *,
    min_bucket_examples: int = DEFAULT_MIN_BUCKET_EXAMPLES,
    feature_config: OracleMemoryFeatureConfig | None = None,
    success_threshold: float = DEFAULT_SUCCESS_THRESHOLD,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    steps: int = DEFAULT_TRAINING_STEPS,
    l2: float = DEFAULT_L2,
    training_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not examples:
        raise ValueError("cannot train oracle memory policy from zero examples")

    feature_config = feature_config or OracleMemoryFeatureConfig()
    template_counts = Counter()
    bucket_counts = Counter()
    decision_counts = Counter()
    fully_certified_counts = Counter()
    by_problem_id: dict[str, set[str]] = defaultdict(set)
    bucket_mapping: dict[str, str] = {}

    for example in examples:
        problem_id = str(example.get("problem_id") or "").strip()
        template_name = str(example.get("selected_template_name") or "").strip()
        bucket_name = str(example.get("recipe_bucket") or recipe_bucket_from_template_name(template_name)).strip()
        bucket_counts[bucket_name] += 1
        if template_name:
            template_counts[template_name] += 1
            bucket_mapping[template_name] = bucket_name
        if problem_id:
            by_problem_id[problem_id].add(bucket_name)
        decision_key = "accept" if str(example.get("decision") or "") == "accept" else "reject"
        decision_counts[(bucket_name, decision_key)] += 1
        fully_key = (
            "fully_certified"
            if str(example.get("reward_reason") or "") == "fully_certified"
            else "not_fully_certified"
        )
        fully_certified_counts[(bucket_name, fully_key)] += 1

    coverage_hist = Counter(len(bucket_names) for bucket_names in by_problem_id.values())
    recipe_bucket_summary = {
        "total_rows": len(examples),
        "unique_problem_ids": len(by_problem_id),
        "unique_templates": len(template_counts),
        "template_counts": dict(template_counts.most_common()),
        "bucket_mapping": bucket_mapping,
        "bucket_counts": {bucket_name: bucket_counts.get(bucket_name, 0) for bucket_name in sorted(bucket_counts)},
        "decision_counts": {
            bucket_name: {
                "accept": decision_counts.get((bucket_name, "accept"), 0),
                "reject": decision_counts.get((bucket_name, "reject"), 0),
            }
            for bucket_name in sorted(bucket_counts)
        },
        "fully_certified_counts": {
            bucket_name: {
                "fully_certified": fully_certified_counts.get((bucket_name, "fully_certified"), 0),
                "not_fully_certified": fully_certified_counts.get((bucket_name, "not_fully_certified"), 0),
            }
            for bucket_name in sorted(bucket_counts)
        },
        "problem_bucket_coverage_histogram": dict(sorted(coverage_hist.items())),
        "multi_bucket_problem_count": sum(1 for buckets in by_problem_id.values() if len(buckets) >= 2),
        "max_observed_buckets_per_problem": max((len(buckets) for buckets in by_problem_id.values()), default=0),
        "min_bucket_examples": int(min_bucket_examples),
        "support_gate_passed": all(count >= min_bucket_examples for count in bucket_counts.values()) if bucket_counts else False,
    }
    oof_predictions = compute_group_oof_predictions(
        examples,
        feature_config=feature_config,
        success_threshold=success_threshold,
        learning_rate=learning_rate,
        steps=steps,
        l2=l2,
    )
    selection_summary = summarize_prediction_rows(
        oof_predictions,
        success_threshold=success_threshold,
    )
    selection_summary.update(
        {
            "selection_protocol": {
                "group_cv": "leave_one_problem_out",
                "success_threshold": float(success_threshold),
                "min_bucket_examples": int(min_bucket_examples),
                "description_vocab_cap": int(feature_config.description_vocab_cap),
                "description_min_token_frequency": int(feature_config.description_min_token_frequency),
                "include_action_interactions": bool(feature_config.include_action_interactions),
            },
            "recipe_bucket_summary_snapshot": {
                "bucket_counts": recipe_bucket_summary["bucket_counts"],
                "multi_bucket_problem_count": recipe_bucket_summary["multi_bucket_problem_count"],
                "problem_bucket_coverage_histogram": recipe_bucket_summary["problem_bucket_coverage_histogram"],
            },
        }
    )
    model = fit_oracle_memory_policy(
        examples,
        feature_config=feature_config,
        success_threshold=success_threshold,
        learning_rate=learning_rate,
        steps=steps,
        l2=l2,
        training_metadata=training_metadata,
    )
    return {
        "model": model,
        "selection_summary": selection_summary,
        "recipe_bucket_summary": recipe_bucket_summary,
        "oof_predictions": oof_predictions,
    }


def evaluate_oracle_memory_policy_pipeline(
    *,
    training_examples_csv: Path,
    model_json: Path,
    output_dir: Path,
    prefix: str,
) -> dict[str, Any]:
    examples = load_training_examples_csv(training_examples_csv)
    model = load_oracle_memory_policy_model(model_json)
    probabilities = predict_oracle_memory_policy(model, examples)
    prediction_rows = [
        {
            "problem_id": example["problem_id"],
            "recipe_bucket": example["recipe_bucket"],
            "selected_template_name": example["selected_template_name"],
            "decision": example["decision"],
            "reward_reason": example["reward_reason"],
            "is_success": int(example["is_success"]),
            "is_fully_certified": int(example["is_fully_certified"]),
            "predicted_success_probability": float(probability),
            "predicted_success_label": int(probability >= model.success_threshold),
        }
        for example, probability in zip(examples, probabilities)
    ]
    summary = summarize_prediction_rows(
        prediction_rows,
        success_threshold=model.success_threshold,
    )
    summary.update(
        {
            "evaluation_protocol": {
                "kind": "frozen_model_scoring",
                "training_examples_csv": str(training_examples_csv.resolve()),
                "model_json": str(model_json.resolve()),
                "success_threshold": float(model.success_threshold),
            }
        }
    )

    artifacts = {
        "eval_summary_json": write_summary_json(
            summary=summary,
            output_dir=output_dir,
            prefix=prefix,
            suffix="eval_summary",
        )
    }
    if summary["ranking_analysis"]["supported"]:
        artifacts["problem_rankings_csv"] = write_problem_rankings_csv(
            ranking_rows=summary["problem_rankings"],
            output_dir=output_dir,
            prefix=prefix,
        )
    return {
        "examples": examples,
        "prediction_rows": prediction_rows,
        "summary": summary,
        "artifacts": artifacts,
    }
