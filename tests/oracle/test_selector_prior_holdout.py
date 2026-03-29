import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_selector_prior_holdout_subset import main as build_subset_main
from scripts.evaluate_selector_prior_holdout import main as evaluate_holdout_main
from src.oracle.selector_prior import build_curated_training_rows, fit_selector_prior
from src.oracle.selector_prior_holdout import (
    build_holdout_subset,
    evaluate_selector_prior_external_holdout,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def _dataset_row(problem_id: str, tags: list[str] | None = None) -> dict[str, object]:
    return {
        "id": problem_id,
        "description": f"description for {problem_id}",
        "correct_solution": [{"code": "print(1)"}],
        "test_case": [{"input": "1\n", "output": "1\n"}],
        "tags": tags or [],
    }


def _selector_row(
    problem_id: str,
    *,
    selected_family_id: str,
    canonical_tags_joined: str = "",
    problem_tags_joined: str = "",
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
        "problem_tags_joined": problem_tags_joined,
        "canonical_tags_joined": canonical_tags_joined,
        "problem_type_joined": "",
        "key_elements_joined": "",
        "objective_text": "",
        "graph_type": "",
        "is_multi_solution": 0,
        "data_structures_joined": "",
        "constraints_json": "",
        "description_chars": 1000,
        "public_tests_count": 20,
        "is_trusted_label": 1,
        "sample_weight": 1.0,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_model_json(
    path: Path,
    rows: list[dict[str, object]],
    *,
    trusted_csv_path: Path | None = None,
    training_metadata: dict[str, object] | None = None,
) -> None:
    curated = build_curated_training_rows(rows)
    model = fit_selector_prior(curated)
    payload = {
        "feature_names": list(model.feature_names),
        "weights": [float(weight) for weight in model.weights],
        "numeric_stats": model.numeric_stats,
        "label_mapping": model.label_mapping,
        "learning_rate": model.learning_rate,
        "steps": model.steps,
        "l2": model.l2,
    }
    if training_metadata is None and trusted_csv_path is not None:
        training_metadata = {
            "trusted_csv_path": str(trusted_csv_path.resolve()),
            "trusted_csv_sha256": _sha256_file(trusted_csv_path),
            "num_examples": len(curated),
            "problem_ids": sorted({row.problem_id for row in curated}),
            "label_distribution": {
                "oracle.dp.topdown": sum(1 for row in curated if row.label_family_id == "oracle.dp.topdown"),
                "oracle.enumeration.n_nested_loops": sum(
                    1 for row in curated if row.label_family_id == "oracle.enumeration.n_nested_loops"
                ),
            },
            "cohort_priority": ["selected_family", "rerun", "unknown"],
            "eval_protocol": "leave_one_problem_out",
        }
    if training_metadata is not None:
        payload["training_metadata"] = training_metadata
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def test_build_holdout_subset_excludes_dev_ids_and_respects_offset(tmp_path: Path):
    dataset_path = tmp_path / "dataset.jsonl"
    output_path = tmp_path / "subset.jsonl"
    _write_jsonl(
        dataset_path,
        [
            _dataset_row("p1"),
            _dataset_row("p2"),
            _dataset_row("p3"),
            _dataset_row("p4"),
            _dataset_row("p5"),
            _dataset_row("p6"),
        ],
    )

    result = build_holdout_subset(
        dataset_path=dataset_path,
        output_path=output_path,
        excluded_problem_ids={"p2", "p5"},
        offset=1,
        limit=2,
    )

    written_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

    assert result["problem_ids"] == ["p3", "p4"]
    assert result["overlap_count"] == 0
    assert [row["id"] for row in written_rows] == ["p3", "p4"]


def test_build_selector_prior_holdout_subset_cli_writes_expected_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    dataset_path = tmp_path / "dataset.jsonl"
    exclude_csv = tmp_path / "dev.csv"
    output_path = tmp_path / "subset.jsonl"
    _write_jsonl(dataset_path, [_dataset_row("p1"), _dataset_row("p2"), _dataset_row("p3")])
    _write_csv(
        exclude_csv,
        [
            {"problem_id": "p2", "is_trusted_label": 1, "selected_family_id": "oracle.dp.topdown"},
        ],
    )

    exit_code = build_subset_main(
        [
            "--dataset",
            str(dataset_path),
            "--exclude-trusted-csv",
            str(exclude_csv),
            "--output",
            str(output_path),
            "--limit",
            "2",
        ]
    )

    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert output_path.exists()
    assert '"overlap_count": 0' in stdout


def test_build_selector_prior_holdout_subset_cli_supports_exclude_jsonl_sources(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    dataset_path = tmp_path / "dataset.jsonl"
    exclude_csv = tmp_path / "dev.csv"
    exclude_jsonl_a = tmp_path / "batch2.jsonl"
    exclude_jsonl_b = tmp_path / "batch3.jsonl"
    output_path = tmp_path / "subset.jsonl"
    _write_jsonl(
        dataset_path,
        [_dataset_row("p1"), _dataset_row("p2"), _dataset_row("p3"), _dataset_row("p4"), _dataset_row("p5")],
    )
    _write_csv(
        exclude_csv,
        [
            {"problem_id": "p2", "is_trusted_label": 1, "selected_family_id": "oracle.dp.topdown"},
        ],
    )
    _write_jsonl(exclude_jsonl_a, [{"id": "p3"}])
    _write_jsonl(exclude_jsonl_b, [{"problem_id": "p4"}])

    exit_code = build_subset_main(
        [
            "--dataset",
            str(dataset_path),
            "--exclude-trusted-csv",
            str(exclude_csv),
            "--exclude-jsonl",
            str(exclude_jsonl_a),
            "--exclude-jsonl",
            str(exclude_jsonl_b),
            "--output",
            str(output_path),
            "--limit",
            "2",
        ]
    )

    stdout = capsys.readouterr().out
    written_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]

    assert exit_code == 0
    assert [row["id"] for row in written_rows] == ["p1", "p5"]
    assert '"overlap_count": 0' in stdout


def test_evaluate_selector_prior_external_holdout_raises_on_overlap(tmp_path: Path):
    dev_csv = tmp_path / "dev.csv"
    holdout_csv = tmp_path / "holdout.csv"
    model_json = tmp_path / "model.json"

    dev_rows = [
        _selector_row("p_dev_overlap", selected_family_id="oracle.dp.topdown", canonical_tags_joined="graphs"),
        _selector_row("p_dev_2", selected_family_id="oracle.enumeration.n_nested_loops", canonical_tags_joined="math"),
    ]
    holdout_rows = [
        _selector_row("p_dev_overlap", selected_family_id="oracle.dp.topdown", canonical_tags_joined="graphs"),
    ]

    _write_csv(dev_csv, dev_rows)
    _write_csv(holdout_csv, holdout_rows)
    _write_model_json(model_json, dev_rows, trusted_csv_path=dev_csv)

    with pytest.raises(ValueError, match="overlap"):
        evaluate_selector_prior_external_holdout(
            dev_trusted_csv=dev_csv,
            holdout_trusted_csv=holdout_csv,
            dev_model_json=model_json,
        )


def test_evaluate_selector_prior_external_holdout_raises_on_model_provenance_mismatch(tmp_path: Path):
    dev_csv = tmp_path / "dev.csv"
    holdout_csv = tmp_path / "holdout.csv"
    model_json = tmp_path / "model.json"

    dev_rows = [
        _selector_row("p_dev_1", selected_family_id="oracle.dp.topdown", canonical_tags_joined="graphs"),
        _selector_row(
            "p_dev_2",
            selected_family_id="oracle.enumeration.n_nested_loops",
            canonical_tags_joined="math",
        ),
    ]
    holdout_rows = [
        _selector_row("p_holdout_1", selected_family_id="oracle.dp.topdown", canonical_tags_joined="graphs"),
    ]

    _write_csv(dev_csv, dev_rows)
    _write_csv(holdout_csv, holdout_rows)
    _write_model_json(
        model_json,
        dev_rows,
        training_metadata={
            "trusted_csv_path": str((tmp_path / "other.csv").resolve()),
            "trusted_csv_sha256": "deadbeef",
            "num_examples": 2,
            "problem_ids": ["p_dev_1", "p_other"],
            "cohort_priority": ["selected_family", "rerun", "unknown"],
            "eval_protocol": "leave_one_problem_out",
        },
    )

    with pytest.raises(ValueError, match="model provenance mismatch"):
        evaluate_selector_prior_external_holdout(
            dev_trusted_csv=dev_csv,
            holdout_trusted_csv=holdout_csv,
            dev_model_json=model_json,
        )


def test_evaluate_selector_prior_holdout_cli_writes_expected_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    dev_csv = tmp_path / "dev.csv"
    holdout_csv = tmp_path / "holdout.csv"
    model_json = tmp_path / "model.json"
    output_dir = tmp_path / "out"

    dev_rows = [
        _selector_row("p_dev_dp_graphs", selected_family_id="oracle.dp.topdown", canonical_tags_joined="graphs"),
        _selector_row("p_dev_dp_greedy", selected_family_id="oracle.dp.topdown", canonical_tags_joined="greedy"),
        _selector_row("p_dev_enum_math", selected_family_id="oracle.enumeration.n_nested_loops", canonical_tags_joined="math"),
        _selector_row("p_dev_enum_bf_math", selected_family_id="oracle.enumeration.n_nested_loops", canonical_tags_joined="brute force|math"),
    ]
    holdout_rows = [
        _selector_row("p_holdout_math", selected_family_id="oracle.enumeration.n_nested_loops", canonical_tags_joined="math"),
        _selector_row("p_holdout_graphs_math", selected_family_id="oracle.dp.topdown", canonical_tags_joined="graphs|math"),
    ]

    _write_csv(dev_csv, dev_rows)
    _write_csv(holdout_csv, holdout_rows)
    _write_model_json(model_json, dev_rows, trusted_csv_path=dev_csv)

    exit_code = evaluate_holdout_main(
        [
            "--dev-trusted-csv",
            str(dev_csv),
            "--holdout-trusted-csv",
            str(holdout_csv),
            "--dev-model-json",
            str(model_json),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "selector_prior_holdout_cli",
        ]
    )

    stdout = capsys.readouterr().out
    summary = json.loads(
        (output_dir / "selector_prior_holdout_cli_summary.json").read_text(encoding="utf-8")
    )
    prediction_rows = list(
        csv.DictReader((output_dir / "selector_prior_holdout_cli_predictions.csv").open("r", encoding="utf-8"))
    )

    assert exit_code == 0
    assert summary["evaluation_kind"] == "external_holdout_dev_to_external_holdout"
    assert summary["dev_holdout_overlap_count"] == 0
    assert "logistic_holdout_accuracy" in summary
    assert "rule_has_math_accuracy" in summary
    assert "rule_small_math_pattern_accuracy" in summary
    assert summary["baseline_metrics"]["always_dp"]["dp_recall"] == 1.0
    assert summary["baseline_metrics"]["always_dp"]["enumeration_recall"] == 0.0
    assert summary["baseline_metrics"]["always_dp"]["confusion_matrix"] == {
        "oracle.dp.topdown": {
            "oracle.dp.topdown": 1,
            "oracle.enumeration.n_nested_loops": 0,
        },
        "oracle.enumeration.n_nested_loops": {
            "oracle.dp.topdown": 1,
            "oracle.enumeration.n_nested_loops": 0,
        },
    }
    assert summary["baseline_metrics"]["rule_small_math_pattern"]["dp_recall"] == 1.0
    assert summary["baseline_metrics"]["rule_small_math_pattern"]["enumeration_recall"] == 1.0
    assert summary["baseline_metrics"]["rule_small_math_pattern"]["confusion_matrix"] == {
        "oracle.dp.topdown": {
            "oracle.dp.topdown": 1,
            "oracle.enumeration.n_nested_loops": 0,
        },
        "oracle.enumeration.n_nested_loops": {
            "oracle.dp.topdown": 0,
            "oracle.enumeration.n_nested_loops": 1,
        },
    }
    assert len(prediction_rows) == 2
    assert prediction_rows[0]["canonical_tags_joined"] in {"math", "graphs|math"}
    assert "logistic_holdout_accuracy" in stdout
