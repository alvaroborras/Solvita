import csv
import json
from pathlib import Path

import pytest

from scripts.diagnose_selector_prior_baselines import main
from src.oracle.selector_prior import build_curated_training_rows
from src.oracle.selector_prior_diagnostics import evaluate_selector_prior_diagnostics


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
    canonical_tags_joined: str = "",
    problem_tags_joined: str = "",
    description_chars: int = 1000,
    public_tests_count: int = 20,
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
        "candidate_family_pool_size": len(pool),
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
        "description_chars": description_chars,
        "public_tests_count": public_tests_count,
        "is_trusted_label": 1,
        "sample_weight": 1.0,
    }


def _curated_rows() -> list:
    return build_curated_training_rows(
        [
            _row(
                "p_enum_math",
                source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
                description_chars=700,
                public_tests_count=10,
            ),
            _row(
                "p_enum_bruteforce_math",
                source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="brute force|math",
                description_chars=900,
                public_tests_count=12,
            ),
            _row(
                "p_dp_bruteforce",
                source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="brute force",
                description_chars=1300,
                public_tests_count=30,
            ),
            _row(
                "p_dp_graphs",
                source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="graphs",
                description_chars=1700,
                public_tests_count=40,
            ),
            _row(
                "p_dp_graphs_math",
                source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="graphs|math",
                description_chars=1800,
                public_tests_count=50,
            ),
        ]
    )


def test_evaluate_selector_prior_diagnostics_reports_rule_baselines():
    result = evaluate_selector_prior_diagnostics(_curated_rows())

    assert result["summary"]["num_examples"] == 5
    assert result["summary"]["always_dp_accuracy"] == 0.6
    assert result["summary"]["rule_has_math_accuracy"] == 0.8
    assert result["summary"]["rule_small_math_pattern_accuracy"] == 1.0

    predictions = {row["problem_id"]: row for row in result["predictions"]}
    assert predictions["p_dp_graphs_math"]["rule_has_math_prediction"] == "oracle.enumeration.n_nested_loops"
    assert predictions["p_dp_graphs_math"]["rule_small_math_pattern_prediction"] == "oracle.dp.topdown"
    assert predictions["p_enum_math"]["rule_small_math_pattern_correct"] == 1


def test_diagnose_selector_prior_baselines_cli_writes_expected_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    input_csv = tmp_path / "trusted.csv"
    output_dir = tmp_path / "out"
    _write_csv(input_csv, _curated_rows_to_csv_rows())

    exit_code = main(
        [
            "--input-csv",
            str(input_csv),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "selector_prior_diag_cli",
        ]
    )

    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert (output_dir / "selector_prior_diag_cli_summary.json").exists()
    assert (output_dir / "selector_prior_diag_cli_predictions.csv").exists()
    assert "rule_has_math_accuracy" in stdout
    assert "rule_small_math_pattern_accuracy" in stdout


def _curated_rows_to_csv_rows() -> list[dict[str, object]]:
    return [
        _row(
            "p_enum_math",
            source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            canonical_tags_joined="math",
            description_chars=700,
            public_tests_count=10,
        ),
        _row(
            "p_enum_bruteforce_math",
            source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.enumeration.n_nested_loops",
            canonical_tags_joined="brute force|math",
            description_chars=900,
            public_tests_count=12,
        ),
        _row(
            "p_dp_bruteforce",
            source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            canonical_tags_joined="brute force",
            description_chars=1300,
            public_tests_count=30,
        ),
        _row(
            "p_dp_graphs",
            source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            canonical_tags_joined="graphs",
            description_chars=1700,
            public_tests_count=40,
        ),
        _row(
            "p_dp_graphs_math",
            source_path="/runs/oracle_pilot_20_w12_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
            selected_family_id="oracle.dp.topdown",
            canonical_tags_joined="graphs|math",
            description_chars=1800,
            public_tests_count=50,
        ),
    ]
