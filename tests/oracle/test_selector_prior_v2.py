import csv
import json
from pathlib import Path

import pytest

from scripts.train_selector_prior_v2 import main as train_v2_main
from src.oracle.selector_prior import build_curated_training_rows
from src.oracle.selector_prior_v2 import (
    _fit_weighted_binary_logreg,
    _sigmoid,
    SelectorPriorV2FeatureSwitches,
    compute_selector_prior_v2_oof_predictions,
    fit_selector_prior_v2,
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
    canonical_tags_joined: str = "",
    problem_tags_joined: str = "",
    problem_type_joined: str = "",
    key_elements_joined: str = "",
    objective_text: str = "",
    graph_type: str = "",
    is_multi_solution: int = 0,
    data_structures_joined: str = "",
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
        "problem_type_joined": problem_type_joined,
        "key_elements_joined": key_elements_joined,
        "objective_text": objective_text,
        "graph_type": graph_type,
        "is_multi_solution": is_multi_solution,
        "data_structures_joined": data_structures_joined,
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
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
                problem_type_joined="constructive algorithms",
                key_elements_joined="counting|patterns",
                objective_text="Count valid patterns with simple arithmetic reasoning",
                graph_type="",
                data_structures_joined="arrays",
                description_chars=700,
                public_tests_count=8,
            ),
            _row(
                "p_enum_unique",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="brute force|math",
                problem_type_joined="implementation",
                key_elements_joined="simulation|cases",
                objective_text="Enumerate local_unique_token cases carefully",
                graph_type="",
                data_structures_joined="vectors",
                description_chars=900,
                public_tests_count=12,
            ),
            _row(
                "p_dp_graphs",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp|graphs",
                problem_type_joined="dynamic programming",
                key_elements_joined="states|transitions",
                objective_text="Compute optimal transitions on graph states",
                graph_type="dag",
                data_structures_joined="graphs|arrays",
                is_multi_solution=1,
                description_chars=1600,
                public_tests_count=30,
            ),
            _row(
                "p_dp_trees",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp|trees",
                problem_type_joined="dynamic programming",
                key_elements_joined="dfs|memoization",
                objective_text="Memoize subtree values on rooted trees",
                graph_type="tree",
                data_structures_joined="trees|maps",
                description_chars=1800,
                public_tests_count=35,
            ),
        ]
    )


def test_fit_selector_prior_v2_supports_positive_class_weight():
    rows = _curated_rows()
    feature_switches = SelectorPriorV2FeatureSwitches(objective_text_vocab_cap=50)

    model = fit_selector_prior_v2(rows, positive_class_weight=1.5, feature_switches=feature_switches)

    assert model.positive_class_weight == 1.5
    assert model.feature_switches.objective_text_vocab_cap == 50


def test_fit_weighted_binary_logreg_upweights_enumeration_class():
    X = __import__("numpy").array(
        [
            [1.0, 0.0],
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
        ],
        dtype=float,
    )
    y = __import__("numpy").array([0.0, 1.0, 1.0, 1.0, 1.0], dtype=float)

    default_weights = _fit_weighted_binary_logreg(X, y, positive_class_weight=1.0)
    weighted_weights = _fit_weighted_binary_logreg(X, y, positive_class_weight=2.0)

    default_enum_dp_probability = float(_sigmoid(X[:1] @ default_weights)[0])
    weighted_enum_dp_probability = float(_sigmoid(X[:1] @ weighted_weights)[0])

    assert weighted_enum_dp_probability < default_enum_dp_probability


def test_compute_selector_prior_v2_oof_predictions_uses_fold_local_vocab():
    rows = _curated_rows()
    feature_switches = SelectorPriorV2FeatureSwitches(objective_text_vocab_cap=100)

    result = compute_selector_prior_v2_oof_predictions(
        rows,
        positive_class_weight=1.0,
        feature_switches=feature_switches,
        return_fold_models=True,
    )

    fold_model = result["fold_models"]["p_enum_unique"]
    assert "local_unique_token" not in set(fold_model.objective_text_vocabulary)


def test_fit_selector_prior_v2_uses_extended_feature_switches():
    rows = _curated_rows()

    without_objective = fit_selector_prior_v2(
        rows,
        positive_class_weight=1.0,
        feature_switches=SelectorPriorV2FeatureSwitches(objective_text_vocab_cap=0),
    )
    with_objective = fit_selector_prior_v2(
        rows,
        positive_class_weight=1.0,
        feature_switches=SelectorPriorV2FeatureSwitches(objective_text_vocab_cap=50),
    )

    assert "joined::problem_type::dynamic programming" in with_objective.feature_names
    assert "joined::key_elements::states" in with_objective.feature_names
    assert "graph_type::dag" in with_objective.feature_names
    assert "joined::data_structures::graphs" in with_objective.feature_names
    assert "flag::is_multi_solution" in with_objective.feature_names
    assert not any(name.startswith("objective::") for name in without_objective.feature_names)
    assert any(name.startswith("objective::") for name in with_objective.feature_names)


def test_train_selector_prior_v2_cli_writes_complete_selection_summary(
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
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="math",
                problem_type_joined="implementation",
                key_elements_joined="cases",
                objective_text="Count arithmetic patterns carefully",
                data_structures_joined="arrays",
                description_chars=800,
                public_tests_count=10,
            ),
            _row(
                "p2",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.enumeration.n_nested_loops",
                canonical_tags_joined="brute force|math",
                problem_type_joined="implementation",
                key_elements_joined="simulation",
                objective_text="Enumerate small cases with loops",
                data_structures_joined="vectors",
                description_chars=900,
                public_tests_count=12,
            ),
            _row(
                "p3",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp|graphs",
                problem_type_joined="dynamic programming",
                key_elements_joined="states|transitions",
                objective_text="Optimize graph transitions with dp states",
                graph_type="dag",
                data_structures_joined="graphs|arrays",
                is_multi_solution=1,
                description_chars=1700,
                public_tests_count=30,
            ),
            _row(
                "p4",
                source_path="/runs/oracle_pilot_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
                selected_family_id="oracle.dp.topdown",
                canonical_tags_joined="dp|trees",
                problem_type_joined="dynamic programming",
                key_elements_joined="dfs|memoization",
                objective_text="Memoize subtree answers on rooted trees",
                graph_type="tree",
                data_structures_joined="trees|maps",
                description_chars=1850,
                public_tests_count=35,
            ),
        ],
    )

    exit_code = train_v2_main(
        [
            "--input-csv",
            str(input_csv),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "selector_prior_v2_cli",
        ]
    )

    stdout = capsys.readouterr().out
    summary = json.loads(
        (output_dir / "selector_prior_v2_cli_selection_summary.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert (output_dir / "selector_prior_v2_cli_model.json").exists()
    assert (output_dir / "selector_prior_v2_cli_feature_weights.csv").exists()
    assert (output_dir / "selector_prior_v2_cli_oof_predictions.csv").exists()
    assert summary["chosen_positive_class_weight"] in {1.0, 1.25, 1.5, 2.0}
    assert 0.2 <= summary["chosen_threshold"] <= 0.8
    assert "chosen_feature_switches" in summary
    assert "success_criteria" in summary
    assert "single_example_balanced_accuracy_swing_threshold" in summary
    assert summary["selection_protocol"]["vocab_fitting_scope"] == "fold_train_only"
    assert summary["selection_protocol"]["uses_external_holdout"] is False
    assert "chosen_threshold" in stdout
