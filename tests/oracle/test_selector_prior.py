import csv
import json
from pathlib import Path

import pytest

from scripts.train_selector_prior import main
from src.oracle.selector_prior import (
    ALLOWED_FEATURE_COLUMNS,
    LEAKY_FEATURE_COLUMNS,
    build_curated_training_rows,
    build_feature_frame,
    evaluate_selector_prior,
    load_selector_prior_rows,
)


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


def _row(
    problem_id: str,
    *,
    source_path: str,
    selected_family_id: str,
    candidate_family_pool: list[str] | None = None,
    canonical_tags_joined: str = "",
    problem_tags_joined: str = "",
    description_chars: int = 1000,
    public_tests_count: int = 20,
    decision: str = "accept",
    artifact_kind: str = "expected_output",
    reward_reason: str = "fully_certified",
    selected_template_name: str = "Leaky Template",
    cost_llm_calls: int = 7,
) -> dict[str, object]:
    pool = candidate_family_pool or [
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
        "candidate_family_pool_size": len(pool),
        "candidate_family_pool_joined": "|".join(pool),
        "selected_family_id": selected_family_id,
        "fallback_family_id": pool[1] if len(pool) > 1 else "",
        "selected_is_fallback": int(len(pool) > 1 and selected_family_id == pool[1]),
        "decision": decision,
        "artifact_kind": artifact_kind,
        "compile_success": 1,
        "public_self_check_pass": 1,
        "probe_pack_pass": 1,
        "certified_count": 50,
        "certified_target_count": 50,
        "cert_ratio": 1.0,
        "reward": 1.0,
        "reward_reason": reward_reason,
        "failure_stage": "",
        "failure_subtype": "",
        "checker_fallback_used": 0,
        "solver_attempt_count": 2,
        "selected_template_name": selected_template_name,
        "compact_retry_count": 0,
        "cost_llm_calls": cost_llm_calls,
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
        "description_chars": description_chars,
        "public_tests_count": public_tests_count,
        "is_trusted_label": 1,
        "sample_weight": 1.0,
    }


def test_load_selector_prior_rows_keeps_only_trusted_rows(tmp_path: Path):
    input_csv = tmp_path / "rows.csv"
    _write_csv(
        input_csv,
        [
            _row(
                "trusted",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
            ),
            {
                **_row(
                    "untrusted",
                    source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                    selected_family_id="oracle.enumeration.n_nested_loops",
                ),
                "is_trusted_label": 0,
            },
        ],
    )

    rows = load_selector_prior_rows(input_csv)

    assert [row["problem_id"] for row in rows] == ["trusted"]


def test_build_curated_training_rows_prefers_higher_priority_cohort_and_dedupes_same_label():
    rows = [
        _row(
            "p_conflict",
            source_path="/runs/oracle_pilot_20_w12_rerun_20260327T021826Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            canonical_tags_joined="graphs",
        ),
        _row(
            "p_conflict",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            canonical_tags_joined="graphs",
        ),
        _row(
            "p_same_label",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            canonical_tags_joined="math",
        ),
        _row(
            "p_same_label",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            canonical_tags_joined="math",
        ),
    ]

    curated = build_curated_training_rows(rows)

    assert [row.problem_id for row in curated] == ["p_conflict", "p_same_label"]
    assert curated[0].label_family_id == "oracle.dp.topdown"
    assert curated[0].label_cohort == "selected_family"
    assert curated[1].label_family_id == "oracle.enumeration.n_nested_loops"


def test_build_curated_training_rows_raises_on_same_priority_conflict():
    rows = [
        _row(
            "p_bad",
            source_path="/runs/custom_selected_family_a/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            canonical_tags_joined="dp",
        ),
        _row(
            "p_bad",
            source_path="/runs/custom_selected_family_b/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            canonical_tags_joined="dp",
        ),
    ]

    with pytest.raises(ValueError, match="same-priority label conflict"):
        build_curated_training_rows(rows, cohort_priority=("selected_family",))


def test_build_curated_training_rows_raises_on_same_label_feature_mismatch():
    rows = [
        _row(
            "p_mismatch",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            canonical_tags_joined="dp",
            description_chars=1000,
        ),
        _row(
            "p_mismatch",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            canonical_tags_joined="dp",
            description_chars=2000,
        ),
    ]

    with pytest.raises(ValueError, match="same-label feature mismatch"):
        build_curated_training_rows(rows)


def test_build_curated_training_rows_raises_when_pool_contains_unsupported_family():
    rows = [
        _row(
            "p_pool_bad",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            candidate_family_pool=[
                "oracle.dp.topdown",
                "oracle.graph.dfs",
            ],
        )
    ]

    with pytest.raises(ValueError, match="unsupported family in candidate_family_pool"):
        build_curated_training_rows(rows)


def test_build_curated_training_rows_raises_when_selected_family_not_in_pool():
    rows = [
        _row(
            "p_selected_not_in_pool",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            candidate_family_pool=[
                "oracle.enumeration.n_nested_loops",
                "oracle.enumeration.n_nested_loops",
            ],
        )
    ]

    with pytest.raises(ValueError, match="selected_family_id must be in candidate_family_pool"):
        build_curated_training_rows(rows)


def test_build_curated_training_rows_raises_when_pool_size_is_not_two():
    rows = [
        _row(
            "p_pool_size",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            candidate_family_pool=[
                "oracle.enumeration.n_nested_loops",
            ],
        )
    ]

    with pytest.raises(ValueError, match="candidate_family_pool must contain exactly two families"):
        build_curated_training_rows(rows)


def test_build_curated_training_rows_raises_when_pool_families_are_not_distinct():
    rows = [
        _row(
            "p_pool_duplicate",
            source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            candidate_family_pool=[
                "oracle.enumeration.n_nested_loops",
                "oracle.enumeration.n_nested_loops",
            ],
        )
    ]

    with pytest.raises(ValueError, match="candidate_family_pool must contain two distinct families"):
        build_curated_training_rows(rows)


def test_build_curated_training_rows_normalizes_pool_joined_from_parsed_pool():
    rows = [
        {
            **_row(
                "p_pool_joined_dirty",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                candidate_family_pool=[
                    "oracle.enumeration.n_nested_loops",
                    "oracle.dp.topdown",
                ],
            ),
            "candidate_family_pool_joined": "oracle.dp.topdown|oracle.greedy.two_pointers",
        }
    ]

    curated = build_curated_training_rows(rows)

    assert curated[0].raw_features["candidate_family_pool_joined"] == (
        "oracle.enumeration.n_nested_loops|oracle.dp.topdown"
    )


def test_build_feature_frame_uses_allowlist_and_drops_leaky_columns():
    curated = build_curated_training_rows(
        [
            _row(
                "p1",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp|graphs",
                description_chars=1500,
                public_tests_count=33,
            )
        ]
    )

    feature_frame = build_feature_frame(curated)

    assert set(ALLOWED_FEATURE_COLUMNS).issuperset(
        {
            "candidate_family_pool",
            "canonical_tags_joined",
            "problem_tags_joined",
            "description_chars",
            "public_tests_count",
        }
    )
    assert "tag::dp" in feature_frame.feature_names
    assert "numeric::description_chars_log1p" in feature_frame.feature_names
    assert "family::primary::oracle.enumeration.n_nested_loops" in feature_frame.feature_names
    for leaky_name in LEAKY_FEATURE_COLUMNS:
        assert all(leaky_name not in feature for feature in feature_frame.feature_names)


def test_build_feature_frame_is_unchanged_by_leaky_columns():
    curated = build_curated_training_rows(
        [
            _row(
                "p1",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp|graphs",
                description_chars=1500,
                public_tests_count=33,
                decision="accept",
                reward_reason="fully_certified",
                selected_template_name="Template A",
                cost_llm_calls=1,
            ),
            _row(
                "p2",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp|graphs",
                description_chars=1500,
                public_tests_count=33,
                decision="reject",
                reward_reason="negative_reward",
                selected_template_name="Template B",
                cost_llm_calls=999,
            ),
        ]
    )

    feature_frame = build_feature_frame(curated)

    assert feature_frame.matrix.shape[0] == 2
    assert feature_frame.matrix[0].tolist() == feature_frame.matrix[1].tolist()


def test_evaluate_selector_prior_reports_model_and_weak_baselines():
    curated = build_curated_training_rows(
        [
            _row(
                "p1",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp",
                description_chars=1800,
                public_tests_count=50,
            ),
            _row(
                "p2",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="memoization",
                description_chars=1700,
                public_tests_count=40,
            ),
            _row(
                "p3",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
                description_chars=800,
                public_tests_count=12,
            ),
            _row(
                "p4",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="greedy",
                description_chars=700,
                public_tests_count=10,
            ),
        ]
    )

    result = evaluate_selector_prior(curated, eval_protocol="leave_one_problem_out")

    assert result["summary"]["eval_protocol"] == "leave_one_problem_out"
    assert result["summary"]["num_examples"] == 4
    assert result["summary"]["num_unique_problem_ids"] == 4
    assert result["summary"]["num_folds"] == 4
    assert "model_accuracy" in result["summary"]
    assert "always_primary_accuracy" in result["summary"]
    assert "always_enumeration_accuracy" in result["summary"]
    assert "always_dp_accuracy" in result["summary"]
    assert len(result["predictions"]) == 4


def test_evaluate_selector_prior_single_problem_keeps_prediction_probability_consistent():
    curated = build_curated_training_rows(
        [
            _row(
                "p_single",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                candidate_family_pool=[
                    "oracle.enumeration.n_nested_loops",
                    "oracle.dp.topdown",
                ],
                canonical_tags_joined="math",
                description_chars=700,
                public_tests_count=10,
            )
        ]
    )

    result = evaluate_selector_prior(curated, eval_protocol="leave_one_problem_out")

    prediction = result["predictions"][0]
    assert prediction["predicted_family_id"] == "oracle.enumeration.n_nested_loops"
    assert prediction["predicted_dp_probability"] == 0.0


def test_train_selector_prior_cli_writes_expected_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    input_csv = tmp_path / "trusted.csv"
    output_dir = tmp_path / "out"
    _write_csv(
        input_csv,
        [
            _row(
                "p1",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp",
            ),
            _row(
                "p2",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="memoization",
            ),
            _row(
                "p3",
                source_path="/runs/oracle_pilot_20_w12_selected_family_20260327T025702Z/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )

    exit_code = main(
        [
            "--input-csv",
            str(input_csv),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "selector_prior_cli",
        ]
    )

    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert (output_dir / "selector_prior_cli_curated_examples.csv").exists()
    assert (output_dir / "selector_prior_cli_eval_summary.json").exists()
    assert (output_dir / "selector_prior_cli_eval_predictions.csv").exists()
    assert (output_dir / "selector_prior_cli_model.json").exists()
    assert (output_dir / "selector_prior_cli_feature_weights.csv").exists()
    assert "model_accuracy" in stdout
    assert "always_primary_accuracy" in stdout


def test_train_selector_prior_cli_model_json_contains_training_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    input_csv = tmp_path / "trusted.csv"
    output_dir = tmp_path / "out"
    _write_csv(
        input_csv,
        [
            _row(
                "p1",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="graphs",
            ),
            _row(
                "p2",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
            ),
        ],
    )

    exit_code = main(
        [
            "--input-csv",
            str(input_csv),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "selector_prior_cli",
        ]
    )

    payload = json.loads((output_dir / "selector_prior_cli_model.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["training_metadata"]["trusted_csv_path"] == str(input_csv.resolve())
    assert payload["training_metadata"]["num_examples"] == 2
    assert payload["training_metadata"]["problem_ids"] == ["p1", "p2"]
    assert payload["training_metadata"]["label_distribution"] == {
        "oracle.dp.topdown": 1,
        "oracle.enumeration.n_nested_loops": 1,
    }
    assert payload["training_metadata"]["cohort_priority"] == ["selected_family", "rerun", "unknown"]
    assert payload["training_metadata"]["eval_protocol"] == "leave_one_problem_out"
    assert "trusted_csv_sha256" in payload["training_metadata"]
    assert payload["training_metadata"]["trusted_csv_sha256"]
