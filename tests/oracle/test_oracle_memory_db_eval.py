import csv
import json
import sys
from pathlib import Path

from src.oracle.oracle_memory_db import OracleMemoryDB, observations_to_training_examples
from src.oracle.oracle_memory_policy import (
    load_oracle_memory_policy_model_from_payload,
    predict_oracle_memory_policy,
    summarize_prediction_rows,
    write_training_examples_csv,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.evaluate_oracle_memory_db import main as evaluate_main


def _observation(
    problem_id: str,
    *,
    template_name: str,
    decision: str,
    reward_reason: str,
    description: str,
    tags: list[str],
) -> dict[str, object]:
    bucket = {
        "Top-down Memoized DP": "recipe.dp.memo_default",
        "Greedy Counting Trick": "recipe.specialized.other",
    }[template_name]
    is_success = decision == "accept"
    return {
        "problem_id": problem_id,
        "problem_fingerprint": f"fp-{problem_id}",
        "run_id": "run-train",
        "trial_id": f"trial-{problem_id}",
        "memory_mode": "oracle",
        "policy_version": "v1",
        "action_bucket": bucket,
        "candidate_action_set_json": [bucket],
        "selected_action": bucket,
        "selected_action_propensity": 1.0,
        "exploration_flag": False,
        "template_name": template_name,
        "seed_family": "seed",
        "visible_features_snapshot_json": {
            "description": description,
            "tags": tags,
            "test_case": [{"input": "1\n", "output": "1\n"}],
        },
        "decision": decision,
        "reward": 1.0 if is_success else 0.0,
        "reward_reason": reward_reason,
        "compile_success": is_success,
        "public_self_check_pass": is_success,
        "probe_pack_pass": is_success,
        "certified_count": 1 if is_success else 0,
        "certified_target_count": 1,
        "llm_calls": 1,
        "token_cost": 0.01,
        "source_event_timestamp": "2026-03-28T00:00:00Z",
        "created_at": "2026-03-28T00:00:01Z",
    }


def _build_db_with_snapshot(tmp_path: Path) -> tuple[OracleMemoryDB, dict[str, object]]:
    db = OracleMemoryDB.from_data_dir(tmp_path / "memory")
    db.initialize()
    observations = [
        _observation(
            "train-dp-accept",
            template_name="Top-down Memoized DP",
            decision="accept",
            reward_reason="fully_certified",
            description="Dynamic programming over prefixes and suffixes.",
            tags=["dp", "arrays"],
        ),
        _observation(
            "train-dp-reject",
            template_name="Top-down Memoized DP",
            decision="reject",
            reward_reason="compile_error",
            description="Memoized transitions with invalid base case.",
            tags=["dp"],
        ),
        _observation(
            "train-greedy-accept",
            template_name="Greedy Counting Trick",
            decision="accept",
            reward_reason="success",
            description="Greedy counting over local transitions.",
            tags=["greedy", "strings"],
        ),
    ]
    for row in observations:
        db.insert_observation(row)
    rebuild_result = db.rebuild(snapshot_id="snapshot-eval")
    return db, rebuild_result

def test_evaluate_holdout_returns_external_metrics_gate_and_runtime_sections(tmp_path: Path) -> None:
    db, _ = _build_db_with_snapshot(tmp_path)
    holdout_examples = observations_to_training_examples(
        [
            _observation(
                "holdout-dp",
                template_name="Top-down Memoized DP",
                decision="accept",
                reward_reason="fully_certified",
                description="Dynamic programming with prefix memoization.",
                tags=["dp"],
            ),
            _observation(
                "holdout-greedy",
                template_name="Greedy Counting Trick",
                decision="reject",
                reward_reason="negative_reward",
                description="Greedy local transition counting.",
                tags=["greedy"],
            ),
        ]
    )

    result = db.evaluate_holdout("snapshot-eval", holdout_examples)

    assert "selection_metrics" in result
    assert "external_holdout_metrics" in result
    assert "calibration_gate" in result
    assert "runtime_readiness" in result
    assert result["external_holdout_metrics"]["observed_action_metrics"]["accept_prediction"]["num_examples"] == 2
    assert result["calibration_gate"]["metric_name"] == "accept_prediction"
    assert "ece" in result["calibration_gate"]
    assert "brier_score" in result["calibration_gate"]
    assert result["runtime_readiness"]["state"] in {"offline_only", "holdout_gate_only"}


def test_evaluate_holdout_fails_closed_for_empty_holdout(tmp_path: Path) -> None:
    db, _ = _build_db_with_snapshot(tmp_path)

    result = db.evaluate_holdout("snapshot-eval", [])

    assert result["external_holdout_metrics"]["observed_action_metrics"]["accept_prediction"]["num_examples"] == 0
    assert result["calibration_gate"]["passed"] is False
    assert result["calibration_gate"]["num_examples"] == 0
    assert result["calibration_gate"]["min_examples_required"] >= 1
    assert result["calibration_gate"]["reason"] == "insufficient_holdout_examples"
    assert result["runtime_readiness"]["state"] == "offline_only"


def test_evaluate_holdout_fails_closed_for_single_example_holdout(tmp_path: Path) -> None:
    db, _ = _build_db_with_snapshot(tmp_path)
    holdout_examples = observations_to_training_examples(
        [
            _observation(
                "holdout-single",
                template_name="Top-down Memoized DP",
                decision="accept",
                reward_reason="fully_certified",
                description="Single holdout example with DP memoization.",
                tags=["dp"],
            ),
        ]
    )

    result = db.evaluate_holdout("snapshot-eval", holdout_examples)

    assert result["external_holdout_metrics"]["observed_action_metrics"]["accept_prediction"]["num_examples"] == 1
    assert result["calibration_gate"]["passed"] is False
    assert result["calibration_gate"]["num_examples"] == 1
    assert result["calibration_gate"]["min_examples_required"] > 1
    assert result["calibration_gate"]["reason"] == "insufficient_holdout_examples"
    assert result["runtime_readiness"]["state"] == "offline_only"


def test_evaluate_holdout_uses_snapshot_payload_and_freezes_selection_metrics(tmp_path: Path) -> None:
    db, rebuild_result = _build_db_with_snapshot(tmp_path)
    snapshot = db.get_model_snapshot("snapshot-eval")
    holdout_examples = observations_to_training_examples(
        [
            _observation(
                "holdout-one",
                template_name="Top-down Memoized DP",
                decision="accept",
                reward_reason="fully_certified",
                description="Dynamic programming over grouped states.",
                tags=["dp", "math"],
            ),
            _observation(
                "holdout-two",
                template_name="Greedy Counting Trick",
                decision="reject",
                reward_reason="compile_error",
                description="Greedy local counting with broken invariant.",
                tags=["greedy"],
            ),
        ]
    )

    result = db.evaluate_holdout("snapshot-eval", holdout_examples)

    model = load_oracle_memory_policy_model_from_payload(rebuild_result["model_payload"])
    probabilities = predict_oracle_memory_policy(model, holdout_examples)
    expected_rows = [
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
        for example, probability in zip(holdout_examples, probabilities)
    ]
    expected_summary = summarize_prediction_rows(expected_rows, success_threshold=model.success_threshold)

    assert result["prediction_rows"] == expected_rows
    assert result["external_holdout_metrics"] == expected_summary
    assert snapshot is not None
    assert result["selection_metrics"] == snapshot["metrics"]["selection_summary"]
    assert (
        result["selection_metrics"]["observed_action_metrics"]["accept_prediction"]["num_examples"]
        != result["external_holdout_metrics"]["observed_action_metrics"]["accept_prediction"]["num_examples"]
    )


def test_evaluate_oracle_memory_db_cli_writes_summary_and_predictions(tmp_path: Path) -> None:
    db, _ = _build_db_with_snapshot(tmp_path)
    output_dir = tmp_path / "out"
    holdout_dir = tmp_path / "holdout"
    holdout_examples = observations_to_training_examples(
        [
            _observation(
                "holdout-cli-a",
                template_name="Top-down Memoized DP",
                decision="accept",
                reward_reason="fully_certified",
                description="Dynamic programming with memo tables.",
                tags=["dp"],
            ),
            _observation(
                "holdout-cli-b",
                template_name="Greedy Counting Trick",
                decision="reject",
                reward_reason="negative_reward",
                description="Greedy local transition counting variant.",
                tags=["greedy"],
            ),
        ]
    )
    holdout_csv = write_training_examples_csv(
        examples=holdout_examples,
        output_dir=holdout_dir,
        prefix="oracle_memory_holdout",
    )

    exit_code = evaluate_main(
        [
            "--data-dir",
            str((tmp_path / "memory").resolve()),
            "--snapshot-id",
            "snapshot-eval",
            "--holdout-training-examples-csv",
            str(holdout_csv),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "oracle_memory_eval_cli",
        ]
    )

    assert exit_code == 0
    summary = json.loads((output_dir / "oracle_memory_eval_cli_holdout_summary.json").read_text(encoding="utf-8"))
    prediction_rows = list(
        csv.DictReader((output_dir / "oracle_memory_eval_cli_holdout_predictions.csv").open("r", encoding="utf-8"))
    )

    assert summary["snapshot_id"] == "snapshot-eval"
    assert "selection_metrics" in summary
    assert "external_holdout_metrics" in summary
    assert summary["selection_metrics"] != summary["external_holdout_metrics"]
    assert summary["external_holdout_metrics"]["observed_action_metrics"]["accept_prediction"]["num_examples"] == 2
    assert len(prediction_rows) == 2
