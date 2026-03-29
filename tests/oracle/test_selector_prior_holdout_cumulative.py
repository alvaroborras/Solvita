import csv
import json
from pathlib import Path

import pytest

from scripts.summarize_selector_prior_holdouts import main
from src.oracle.selector_prior_holdout_cumulative import summarize_holdout_predictions


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prediction_row(
    problem_id: str,
    *,
    label_family_id: str,
    logistic_prediction: str,
    always_primary_prediction: str,
    always_enumeration_prediction: str,
    always_dp_prediction: str,
    rule_has_math_prediction: str,
    rule_small_math_pattern_prediction: str,
    canonical_tags_joined: str = "",
    problem_tags_joined: str = "",
) -> dict[str, object]:
    return {
        "problem_id": problem_id,
        "label_family_id": label_family_id,
        "label_cohort": "selected_family",
        "canonical_tags_joined": canonical_tags_joined,
        "problem_tags_joined": problem_tags_joined,
        "logistic_prediction": logistic_prediction,
        "logistic_correct": int(logistic_prediction == label_family_id),
        "logistic_predicted_dp_probability": 0.75 if logistic_prediction == "oracle.dp.topdown" else 0.25,
        "always_primary_prediction": always_primary_prediction,
        "always_primary_correct": int(always_primary_prediction == label_family_id),
        "always_enumeration_prediction": always_enumeration_prediction,
        "always_enumeration_correct": int(always_enumeration_prediction == label_family_id),
        "always_dp_prediction": always_dp_prediction,
        "always_dp_correct": int(always_dp_prediction == label_family_id),
        "rule_has_math_prediction": rule_has_math_prediction,
        "rule_has_math_correct": int(rule_has_math_prediction == label_family_id),
        "rule_small_math_pattern_prediction": rule_small_math_pattern_prediction,
        "rule_small_math_pattern_correct": int(
            rule_small_math_pattern_prediction == label_family_id
        ),
    }


def test_summarize_holdout_predictions_merges_multiple_files(tmp_path: Path):
    csv_a = tmp_path / "batch2.csv"
    csv_b = tmp_path / "batch34.csv"
    _write_csv(
        csv_a,
        [
            _prediction_row(
                "p1",
                label_family_id="oracle.dp.topdown",
                logistic_prediction="oracle.dp.topdown",
                always_primary_prediction="oracle.enumeration.n_nested_loops",
                always_enumeration_prediction="oracle.enumeration.n_nested_loops",
                always_dp_prediction="oracle.dp.topdown",
                rule_has_math_prediction="oracle.dp.topdown",
                rule_small_math_pattern_prediction="oracle.dp.topdown",
                canonical_tags_joined="graphs",
            ),
        ],
    )
    _write_csv(
        csv_b,
        [
            _prediction_row(
                "p2",
                label_family_id="oracle.enumeration.n_nested_loops",
                logistic_prediction="oracle.enumeration.n_nested_loops",
                always_primary_prediction="oracle.enumeration.n_nested_loops",
                always_enumeration_prediction="oracle.enumeration.n_nested_loops",
                always_dp_prediction="oracle.dp.topdown",
                rule_has_math_prediction="oracle.enumeration.n_nested_loops",
                rule_small_math_pattern_prediction="oracle.dp.topdown",
                canonical_tags_joined="math",
            ),
        ],
    )

    result = summarize_holdout_predictions([csv_a, csv_b])

    assert [row["problem_id"] for row in result["predictions"]] == ["p1", "p2"]
    assert result["summary"]["evaluation_kind"] == "cumulative_external_holdout"
    assert result["summary"]["num_examples"] == 2
    assert result["summary"]["num_unique_problem_ids"] == 2
    assert result["summary"]["always_dp_accuracy"] == 0.5
    assert result["summary"]["logistic_accuracy"] == 1.0
    assert result["summary"]["rule_has_math_accuracy"] == 1.0
    assert result["summary"]["baseline_metrics"]["logistic"]["accuracy"] == 1.0
    assert result["summary"]["baseline_metrics"]["logistic"]["dp_recall"] == 1.0
    assert result["summary"]["baseline_metrics"]["logistic"]["enumeration_recall"] == 1.0
    assert result["summary"]["baseline_metrics"]["logistic"]["balanced_accuracy"] == 1.0
    assert result["summary"]["baseline_metrics"]["always_dp"]["balanced_accuracy"] == 0.5
    assert result["summary"]["baseline_metrics"]["always_dp"]["confusion_matrix"] == {
        "oracle.dp.topdown": {
            "oracle.dp.topdown": 1,
            "oracle.enumeration.n_nested_loops": 0,
        },
        "oracle.enumeration.n_nested_loops": {
            "oracle.dp.topdown": 1,
            "oracle.enumeration.n_nested_loops": 0,
        },
    }


def test_summarize_holdout_predictions_raises_on_duplicate_problem_id(tmp_path: Path):
    csv_a = tmp_path / "batch2.csv"
    csv_b = tmp_path / "batch34.csv"
    _write_csv(
        csv_a,
        [
            _prediction_row(
                "p1",
                label_family_id="oracle.dp.topdown",
                logistic_prediction="oracle.dp.topdown",
                always_primary_prediction="oracle.dp.topdown",
                always_enumeration_prediction="oracle.enumeration.n_nested_loops",
                always_dp_prediction="oracle.dp.topdown",
                rule_has_math_prediction="oracle.dp.topdown",
                rule_small_math_pattern_prediction="oracle.dp.topdown",
            ),
        ],
    )
    _write_csv(
        csv_b,
        [
            _prediction_row(
                "p1",
                label_family_id="oracle.enumeration.n_nested_loops",
                logistic_prediction="oracle.enumeration.n_nested_loops",
                always_primary_prediction="oracle.enumeration.n_nested_loops",
                always_enumeration_prediction="oracle.enumeration.n_nested_loops",
                always_dp_prediction="oracle.dp.topdown",
                rule_has_math_prediction="oracle.enumeration.n_nested_loops",
                rule_small_math_pattern_prediction="oracle.dp.topdown",
            ),
        ],
    )

    with pytest.raises(ValueError, match="duplicate problem_id"):
        summarize_holdout_predictions([csv_a, csv_b])


def test_summarize_selector_prior_holdouts_cli_writes_summary_and_predictions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    csv_a = tmp_path / "batch2.csv"
    csv_b = tmp_path / "batch34.csv"
    out = tmp_path / "out"

    _write_csv(
        csv_a,
        [
            _prediction_row(
                "p1",
                label_family_id="oracle.dp.topdown",
                logistic_prediction="oracle.dp.topdown",
                always_primary_prediction="oracle.enumeration.n_nested_loops",
                always_enumeration_prediction="oracle.enumeration.n_nested_loops",
                always_dp_prediction="oracle.dp.topdown",
                rule_has_math_prediction="oracle.dp.topdown",
                rule_small_math_pattern_prediction="oracle.dp.topdown",
            ),
        ],
    )
    _write_csv(
        csv_b,
        [
            _prediction_row(
                "p2",
                label_family_id="oracle.enumeration.n_nested_loops",
                logistic_prediction="oracle.enumeration.n_nested_loops",
                always_primary_prediction="oracle.enumeration.n_nested_loops",
                always_enumeration_prediction="oracle.enumeration.n_nested_loops",
                always_dp_prediction="oracle.dp.topdown",
                rule_has_math_prediction="oracle.enumeration.n_nested_loops",
                rule_small_math_pattern_prediction="oracle.dp.topdown",
            ),
        ],
    )

    exit_code = main(
        [
            "--predictions-csv",
            str(csv_a),
            "--predictions-csv",
            str(csv_b),
            "--output-dir",
            str(out),
            "--prefix",
            "selector_prior_holdout_cumulative",
        ]
    )

    stdout = capsys.readouterr().out
    summary = json.loads(
        (out / "selector_prior_holdout_cumulative_summary.json").read_text(encoding="utf-8")
    )
    prediction_rows = list(
        csv.DictReader(
            (out / "selector_prior_holdout_cumulative_predictions.csv").open("r", encoding="utf-8")
        )
    )

    assert exit_code == 0
    assert summary["num_examples"] == 2
    assert summary["num_unique_problem_ids"] == 2
    assert "always_dp_accuracy" in summary
    assert "logistic_accuracy" in summary
    assert "baseline_metrics" in summary
    assert "balanced_accuracy" in summary["baseline_metrics"]["logistic"]
    assert len(prediction_rows) == 2
    assert prediction_rows[0]["problem_id"] == "p1"
    assert "logistic_accuracy" in stdout
