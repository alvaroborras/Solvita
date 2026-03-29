import csv
import hashlib
import json
import math
from pathlib import Path

import pytest

from scripts.evaluate_selector_prior_v2_holdout import main as evaluate_v2_holdout_main
from src.oracle.selector_prior_v2 import evaluate_selector_prior_v2_external_holdout


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _problem_ids_from_csv(csv_path: Path) -> list[str]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return sorted(
            str(row.get("problem_id") or "")
            for row in csv.DictReader(handle)
            if str(row.get("problem_id") or "")
        )


def _selector_row(
    problem_id: str,
    *,
    selected_family_id: str,
    canonical_tags_joined: str = "",
    objective_text: str = "",
    source_path: str = "/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
) -> dict[str, object]:
    pool = [
        "oracle.enumeration.n_nested_loops",
        "oracle.dp.topdown",
    ]
    return {
        "problem_id": problem_id,
        "source_path": source_path,
        "problem_source_path": "/tmp/problems.jsonl",
        "record_schema_version": "audit_v1",
        "has_audit_fields": 1,
        "has_problem_context": 1,
        "route": "exact_single_answer",
        "trainability_class": "exact_single_answer",
        "candidate_family_pool": json.dumps(pool, ensure_ascii=False),
        "candidate_family_pool_size": 2,
        "candidate_family_pool_joined": "|".join(pool),
        "selected_family_id": selected_family_id,
        "fallback_family_id": pool[1],
        "selected_is_fallback": int(selected_family_id == pool[1]),
        "decision": "accept",
        "artifact_kind": "expected_output",
        "compile_success": 1,
        "public_self_check_pass": 1,
        "probe_pack_pass": 1,
        "certified_count": 50,
        "certified_target_count": 50,
        "cert_ratio": 1.0,
        "reward": 1.0,
        "reward_reason": "fully_certified",
        "failure_stage": "",
        "failure_subtype": "",
        "checker_fallback_used": 0,
        "solver_attempt_count": 2,
        "selected_template_name": "",
        "compact_retry_count": 0,
        "cost_llm_calls": 1,
        "prompt_char_stats": "{}",
        "prompt_chars_generator": 10,
        "prompt_chars_validator": 10,
        "prompt_chars_checker": 10,
        "prompt_chars_solver": 10,
        "problem_tags_joined": canonical_tags_joined,
        "canonical_tags_joined": canonical_tags_joined,
        "problem_type_joined": "",
        "key_elements_joined": "",
        "objective_text": objective_text,
        "graph_type": "",
        "is_multi_solution": 0,
        "data_structures_joined": "",
        "constraints_json": "",
        "description_chars": 1000,
        "public_tests_count": 20,
        "is_trusted_label": 1,
        "sample_weight": 1.0,
    }


def _training_metadata(csv_path: Path, problem_ids: list[str], num_examples: int) -> dict[str, object]:
    return {
        "trusted_csv_path": str(csv_path.resolve()),
        "trusted_csv_sha256": _sha256_file(csv_path),
        "num_examples": num_examples,
        "problem_ids": problem_ids,
        "label_distribution": {},
        "cohort_priority": ["selected_family", "rerun", "unknown"],
        "eval_protocol": "leave_one_problem_out",
    }


def _write_v2_model_json(path: Path, dev_csv: Path) -> None:
    problem_ids = _problem_ids_from_csv(dev_csv)
    metadata = _training_metadata(dev_csv, problem_ids, len(problem_ids))
    payload = {
        "feature_names": ["bias"],
        "weights": [math.log(0.6 / 0.4)],
        "numeric_stats": {
            "numeric::description_chars_log1p": {"mean": 0.0, "std": 1.0},
            "numeric::public_tests_count_log1p": {"mean": 0.0, "std": 1.0},
        },
        "label_mapping": {
            "oracle.enumeration.n_nested_loops": 0,
            "oracle.dp.topdown": 1,
        },
        "learning_rate": 0.1,
        "steps": 400,
        "l2": 0.01,
        "positive_class_weight": 1.25,
        "decision_threshold": 0.7,
        "feature_switches": {
            "use_problem_type_bag": True,
            "use_key_elements_bag": True,
            "use_graph_type": True,
            "use_data_structures_bag": True,
            "use_is_multi_solution": True,
            "objective_text_vocab_cap": 0,
        },
        "objective_text_vocabulary": [],
        "training_metadata": metadata,
        "selection_metadata": {
            "chosen_positive_class_weight": 1.25,
            "chosen_threshold": 0.7,
            "chosen_feature_switches": {
                "use_problem_type_bag": True,
                "use_key_elements_bag": True,
                "use_graph_type": True,
                "use_data_structures_bag": True,
                "use_is_multi_solution": True,
                "objective_text_vocab_cap": 0,
            },
            "success_criteria": {
                "min_accuracy_delta_vs_always_dp": -0.02,
                "min_dp_recall": 0.85,
            },
            "single_example_balanced_accuracy_swing_threshold": 0.25,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_v1_model_json(path: Path, dev_csv: Path) -> None:
    problem_ids = _problem_ids_from_csv(dev_csv)
    metadata = _training_metadata(dev_csv, problem_ids, len(problem_ids))
    payload = {
        "feature_names": ["bias"],
        "weights": [math.log(0.6 / 0.4)],
        "numeric_stats": {
            "numeric::description_chars_log1p": {"mean": 0.0, "std": 1.0},
            "numeric::public_tests_count_log1p": {"mean": 0.0, "std": 1.0},
        },
        "label_mapping": {
            "oracle.enumeration.n_nested_loops": 0,
            "oracle.dp.topdown": 1,
        },
        "learning_rate": 0.1,
        "steps": 400,
        "l2": 0.01,
        "training_metadata": metadata,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def test_evaluate_selector_prior_v2_external_holdout_uses_frozen_threshold_and_reports_metrics(
    tmp_path: Path,
):
    dev_csv = tmp_path / "dev.csv"
    holdout_csv = tmp_path / "batch2_holdout.csv"
    v2_model_json = tmp_path / "selector_prior_v2_model.json"
    v1_model_json = tmp_path / "selector_prior_v1_model.json"

    _write_csv(
        dev_csv,
        [
            _selector_row("p_dev_1", selected_family_id="oracle.dp.topdown", canonical_tags_joined="dp"),
            _selector_row(
                "p_dev_2",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )
    _write_csv(
        holdout_csv,
        [
            _selector_row(
                "p_holdout_dp",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp",
                objective_text="dynamic programming",
            ),
            _selector_row(
                "p_holdout_enum",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
                objective_text="count cases",
            ),
        ],
    )
    _write_v2_model_json(v2_model_json, dev_csv)
    _write_v1_model_json(v1_model_json, dev_csv)

    result = evaluate_selector_prior_v2_external_holdout(
        dev_trusted_csv=dev_csv,
        holdout_trusted_csv=holdout_csv,
        v2_model_json=v2_model_json,
        canonical_v1_dev_trusted_csv=dev_csv,
        canonical_v1_model_json=v1_model_json,
    )

    summary = result["summary"]
    assert summary["chosen_threshold"] == 0.7
    assert summary["frozen_threshold"] == 0.7
    assert "accuracy" in summary
    assert "balanced_accuracy" in summary
    assert "dp_recall" in summary
    assert "enumeration_recall" in summary
    assert "confusion_matrix" in summary
    assert summary["comparison_baselines"]["prior_v1_logistic"]["model_json_path"] == str(
        v1_model_json.resolve()
    )
    assert summary["comparison_baselines"]["prior_v1_logistic"]["dev_trusted_csv_path"] == str(
        dev_csv.resolve()
    )
    assert result["predictions"][0]["v2_prediction"] == "oracle.enumeration.n_nested_loops"


def test_evaluate_selector_prior_v2_external_holdout_raises_on_dev_cohort_mismatch(tmp_path: Path):
    dev_csv = tmp_path / "dev.csv"
    canonical_v1_dev_csv = tmp_path / "canonical_v1_dev.csv"
    holdout_csv = tmp_path / "batch2_holdout.csv"
    v2_model_json = tmp_path / "selector_prior_v2_model.json"
    v1_model_json = tmp_path / "selector_prior_v1_model.json"

    _write_csv(
        dev_csv,
        [
            _selector_row("p_dev_1", selected_family_id="oracle.dp.topdown", canonical_tags_joined="dp"),
            _selector_row(
                "p_dev_2",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )
    _write_csv(
        canonical_v1_dev_csv,
        [
            _selector_row("p_other_1", selected_family_id="oracle.dp.topdown", canonical_tags_joined="dp"),
            _selector_row(
                "p_other_2",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )
    _write_csv(
        holdout_csv,
        [
            _selector_row("p_holdout_dp", selected_family_id="oracle.dp.topdown", canonical_tags_joined="dp"),
            _selector_row(
                "p_holdout_enum",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )
    _write_v2_model_json(v2_model_json, dev_csv)
    _write_v1_model_json(v1_model_json, canonical_v1_dev_csv)

    with pytest.raises(ValueError, match="dev cohort mismatch"):
        evaluate_selector_prior_v2_external_holdout(
            dev_trusted_csv=dev_csv,
            holdout_trusted_csv=holdout_csv,
            v2_model_json=v2_model_json,
            canonical_v1_dev_trusted_csv=canonical_v1_dev_csv,
            canonical_v1_model_json=v1_model_json,
        )


def test_evaluate_selector_prior_v2_holdout_cli_writes_batch_and_cumulative_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    dev_csv = tmp_path / "dev.csv"
    holdout_csv = tmp_path / "selector_dataset_selected_family_batch2_combined_trusted_train_subset.csv"
    v2_model_json = tmp_path / "selector_prior_v2_model.json"
    v1_model_json = tmp_path / "selector_prior_v1_model.json"
    output_dir = tmp_path / "out"

    _write_csv(
        dev_csv,
        [
            _selector_row("p_dev_1", selected_family_id="oracle.dp.topdown", canonical_tags_joined="dp"),
            _selector_row(
                "p_dev_2",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )
    _write_csv(
        holdout_csv,
        [
            _selector_row("p_holdout_dp", selected_family_id="oracle.dp.topdown", canonical_tags_joined="dp"),
            _selector_row(
                "p_holdout_enum",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )
    _write_v2_model_json(v2_model_json, dev_csv)
    _write_v1_model_json(v1_model_json, dev_csv)

    exit_code = evaluate_v2_holdout_main(
        [
            "--dev-trusted-csv",
            str(dev_csv),
            "--v2-model-json",
            str(v2_model_json),
            "--holdout-trusted-csv",
            str(holdout_csv),
            "--canonical-v1-dev-trusted-csv",
            str(dev_csv),
            "--canonical-v1-model-json",
            str(v1_model_json),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "selector_prior_v2_cli",
        ]
    )

    stdout = capsys.readouterr().out
    batch_summary = json.loads(
        (output_dir / "selector_prior_v2_cli_holdout_batch2_summary.json").read_text(encoding="utf-8")
    )
    cumulative_summary = json.loads(
        (output_dir / "selector_prior_v2_cli_holdout_cumulative_summary.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert (output_dir / "selector_prior_v2_cli_holdout_batch2_predictions.csv").exists()
    assert (output_dir / "selector_prior_v2_cli_holdout_cumulative_predictions.csv").exists()
    assert "success_judgment" in batch_summary
    assert "comparison_baselines" in batch_summary
    assert "single_example_balanced_accuracy_swing_threshold" in cumulative_summary
    assert "success_judgment" in stdout
