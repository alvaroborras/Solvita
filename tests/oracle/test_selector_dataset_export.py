import csv
import json
from pathlib import Path

import pytest

from scripts.export_selector_dataset import main
from src.oracle.selector_dataset_export import (
    export_selector_dataset,
    flatten_record_for_csv,
    load_problem_source,
    normalize_candidate_record,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _make_record(problem_id: str, **overrides: object) -> dict:
    record = {
        "problem_id": problem_id,
        "route": "exact_single_answer",
        "trainability_class": "exact_single_answer",
        "candidate_family_pool": [
            "oracle.enumeration.n_nested_loops",
            "oracle.dp.topdown",
        ],
        "selected_family_id": "oracle.dp.topdown",
        "fallback_family_id": "oracle.enumeration.n_nested_loops",
        "decision": "accept",
        "artifact_kind": "expected_output",
        "compile_success": True,
        "public_self_check_pass": True,
        "probe_pack_pass": True,
        "certified_count": 50,
        "certified_target_count": 50,
        "cert_ratio": 1.0,
        "reward": 1.0,
        "reward_reason": "fully_certified",
        "failure_stage": "",
        "failure_subtype": "",
        "checker_fallback_used": False,
        "solver_attempt_count": 2,
        "selected_template_name": "Top-down Memoized DP",
        "compact_retry_count": 0,
        "prompt_char_stats": {
            "generator": 100,
            "validator": 200,
            "checker": 300,
            "solver": 400,
        },
        "cost": {"llm_calls": 6},
    }
    record.update(overrides)
    return record


def test_normalize_candidate_record_supports_legacy_and_audit_schema(tmp_path: Path):
    source_path = tmp_path / "records.jsonl"

    legacy_record = normalize_candidate_record(
        {
            "problem_id": "legacy_problem",
            "route": "exact_single_answer",
            "trainability_class": "exact_single_answer",
            "candidate_family_pool": [
                "oracle.enumeration.n_nested_loops",
                "oracle.dp.topdown",
            ],
            "selected_family_id": "oracle.dp.topdown",
            "compile_success": True,
            "public_self_check_pass": True,
            "probe_pack_pass": True,
        },
        source_path,
    )
    audit_record = normalize_candidate_record(
        _make_record(
            "audit_problem",
            selected_family_id="oracle.greedy.two_pointers",
            fallback_family_id="oracle.greedy.two_pointers",
            candidate_family_pool=[
                "oracle.greedy.two_pointers",
                "oracle.enumeration.n_nested_loops",
                "oracle.dp.topdown",
            ],
        ),
        source_path,
    )

    assert legacy_record["record_schema_version"] == "legacy_v0"
    assert legacy_record["has_audit_fields"] == 0
    assert legacy_record["fallback_family_id"] == ""
    assert legacy_record["decision"] == ""
    assert legacy_record["artifact_kind"] == ""
    assert legacy_record["cost_llm_calls"] == 0
    assert legacy_record["candidate_family_pool_size"] == 2
    assert legacy_record["candidate_family_pool_joined"] == (
        "oracle.enumeration.n_nested_loops|oracle.dp.topdown"
    )
    assert legacy_record["source_path"] == str(source_path)

    assert audit_record["record_schema_version"] == "audit_v1"
    assert audit_record["has_audit_fields"] == 1
    assert audit_record["selected_is_fallback"] == 1
    assert audit_record["cost_llm_calls"] == 6


def test_export_selector_dataset_merges_inputs_and_filters_invalid_records(tmp_path: Path):
    input_a = tmp_path / "records_a.jsonl"
    input_b = tmp_path / "records_b.jsonl"
    output_dir = tmp_path / "out"

    _write_jsonl(
        input_a,
        [
            _make_record("keep_a"),
            _make_record("drop_wrong_route", route="trusted_checker_backed_multi_answer"),
        ],
    )
    _write_jsonl(
        input_b,
        [
            _make_record("keep_b"),
            _make_record(
                "drop_single_pool",
                candidate_family_pool=["oracle.enumeration.n_nested_loops"],
                selected_family_id="oracle.enumeration.n_nested_loops",
            ),
            _make_record(
                "drop_selected_not_in_pool",
                selected_family_id="oracle.graph.dfs",
            ),
        ],
    )

    result = export_selector_dataset(
        input_paths=[input_a, input_b],
        problem_source_path=None,
        output_dir=output_dir,
        prefix="selector_dataset_test",
    )

    audit_rows = _read_jsonl(result["audit_jsonl"])

    assert [row["problem_id"] for row in audit_rows] == ["keep_a", "keep_b"]
    assert result["summary"]["total_input_samples"] == 5
    assert result["summary"]["normalized_samples"] == 5
    assert result["summary"]["audit_all_samples"] == 2
    assert result["summary"]["filtered_samples"] == 3


def test_export_selector_dataset_joins_problem_source_context_fields(tmp_path: Path):
    records_path = tmp_path / "records.jsonl"
    problem_source = tmp_path / "problems.jsonl"
    output_dir = tmp_path / "out"

    _write_jsonl(records_path, [_make_record("p_join")])
    _write_jsonl(
        problem_source,
        [
            {
                "id": "p_join",
                "tags": ["raw_math", "raw_impl"],
                "problem_type": ["raw_type"],
                "key_elements": ["raw_key"],
                "objective": "raw objective",
                "graph_type": "raw_graph",
                "is_multi_solution": True,
                "data_structures": ["raw_ds"],
                "constraints": {"n": "10"},
                "description": "abcde",
                "public_tests": [{"input": "1", "output": "1"}, {"input": "2", "output": "2"}],
                "canonical": {
                    "tags": ["canon_dp", "canon_math"],
                    "problem_type": ["canonical_type"],
                    "key_elements": ["canonical_key"],
                    "objective": "canonical objective",
                    "graph_type": "dag",
                    "is_multi_solution": False,
                    "data_structures": ["segment_tree"],
                    "constraints": {"n": "100000"},
                },
            }
        ],
    )

    result = export_selector_dataset(
        input_paths=[records_path],
        problem_source_path=problem_source,
        output_dir=output_dir,
        prefix="selector_dataset_join",
    )

    audit_row = _read_jsonl(result["audit_jsonl"])[0]

    assert audit_row["has_problem_context"] == 1
    assert audit_row["problem_source_path"] == str(problem_source)
    assert audit_row["problem_tags_joined"] == "raw_math|raw_impl"
    assert audit_row["canonical_tags_joined"] == "canon_dp|canon_math"
    assert audit_row["problem_type_joined"] == "canonical_type"
    assert audit_row["key_elements_joined"] == "canonical_key"
    assert audit_row["objective_text"] == "canonical objective"
    assert audit_row["graph_type"] == "dag"
    assert audit_row["is_multi_solution"] is False
    assert audit_row["data_structures_joined"] == "segment_tree"
    assert audit_row["constraints_json"] == json.dumps({"n": "100000"}, sort_keys=True)
    assert audit_row["description_chars"] == 5
    assert audit_row["public_tests_count"] == 2


def test_export_selector_dataset_without_problem_source_writes_only_audit(tmp_path: Path):
    records_path = tmp_path / "records.jsonl"
    output_dir = tmp_path / "out"
    _write_jsonl(records_path, [_make_record("audit_only")])

    result = export_selector_dataset(
        input_paths=[records_path],
        problem_source_path=None,
        output_dir=output_dir,
        prefix="selector_dataset_no_problem_source",
    )

    audit_row = _read_jsonl(result["audit_jsonl"])[0]

    assert result["trusted_jsonl"] is None
    assert result["trusted_csv"] is None
    assert audit_row["has_problem_context"] == 0
    assert audit_row["problem_source_path"] == ""
    assert audit_row["is_trusted_label"] == 0
    assert audit_row["sample_weight"] == 0.0


def test_export_selector_dataset_trusted_subset_contains_only_trusted_accepts(tmp_path: Path):
    records_path = tmp_path / "records.jsonl"
    problem_source = tmp_path / "problems.jsonl"
    output_dir = tmp_path / "out"

    _write_jsonl(
        records_path,
        [
            _make_record("trusted_keep"),
            _make_record("not_trusted_reward", reward_reason="partial_certification", cert_ratio=0.5),
            _make_record("not_trusted_artifact", artifact_kind=""),
        ],
    )
    _write_jsonl(
        problem_source,
        [
            {"problem_id": "trusted_keep", "description": "a", "public_tests": [], "tags": []},
            {"problem_id": "not_trusted_reward", "description": "b", "public_tests": [], "tags": []},
            {"problem_id": "not_trusted_artifact", "description": "c", "public_tests": [], "tags": []},
        ],
    )

    result = export_selector_dataset(
        input_paths=[records_path],
        problem_source_path=problem_source,
        output_dir=output_dir,
        prefix="selector_dataset_trusted",
    )

    audit_rows = _read_jsonl(result["audit_jsonl"])
    trusted_rows = _read_jsonl(result["trusted_jsonl"])

    assert [row["problem_id"] for row in trusted_rows] == ["trusted_keep"]
    assert trusted_rows[0]["decision"] == "accept"
    assert trusted_rows[0]["artifact_kind"] == "expected_output"
    assert {row["problem_id"]: row["is_trusted_label"] for row in audit_rows} == {
        "trusted_keep": 1,
        "not_trusted_reward": 0,
        "not_trusted_artifact": 0,
    }
    assert {row["problem_id"]: row["sample_weight"] for row in audit_rows} == {
        "trusted_keep": 1.0,
        "not_trusted_reward": 0.0,
        "not_trusted_artifact": 0.0,
    }


def test_flatten_record_for_csv_exposes_expected_columns(tmp_path: Path):
    normalized = normalize_candidate_record(
        _make_record(
            "flatten_me",
            selected_family_id="oracle.greedy.two_pointers",
            fallback_family_id="oracle.greedy.two_pointers",
            candidate_family_pool=[
                "oracle.greedy.two_pointers",
                "oracle.enumeration.n_nested_loops",
                "oracle.dp.topdown",
            ],
        ),
        tmp_path / "records.jsonl",
    )
    normalized["has_problem_context"] = 0
    normalized["problem_source_path"] = ""
    normalized["problem_tags_joined"] = ""
    normalized["canonical_tags_joined"] = ""
    normalized["problem_type_joined"] = ""
    normalized["key_elements_joined"] = ""
    normalized["objective_text"] = ""
    normalized["graph_type"] = ""
    normalized["is_multi_solution"] = False
    normalized["data_structures_joined"] = ""
    normalized["constraints_json"] = ""
    normalized["description_chars"] = 0
    normalized["public_tests_count"] = 0
    normalized["is_trusted_label"] = 0
    normalized["sample_weight"] = 0.0

    flattened = flatten_record_for_csv(normalized)

    assert flattened["cost_llm_calls"] == 6
    assert flattened["prompt_chars_generator"] == 100
    assert flattened["prompt_chars_validator"] == 200
    assert flattened["prompt_chars_checker"] == 300
    assert flattened["prompt_chars_solver"] == 400
    assert flattened["candidate_family_pool_joined"] == (
        "oracle.greedy.two_pointers|oracle.enumeration.n_nested_loops|oracle.dp.topdown"
    )
    assert flattened["selected_is_fallback"] == 1


def test_load_problem_source_rejects_directory(tmp_path: Path):
    problem_dir = tmp_path / "problem_source_dir"
    problem_dir.mkdir()

    with pytest.raises(ValueError, match="single JSONL file"):
        load_problem_source(problem_dir)


def test_load_problem_source_can_limit_to_required_problem_ids(tmp_path: Path):
    problem_source = tmp_path / "problems.jsonl"
    _write_jsonl(
        problem_source,
        [
            {"id": "keep_me", "description": "keep"},
            {"id": "drop_me", "description": "drop"},
        ],
    )

    index = load_problem_source(problem_source, required_problem_ids={"keep_me"})

    assert list(index.keys()) == ["keep_me"]
    assert index["keep_me"]["description"] == "keep"


def test_selector_dataset_cli_writes_expected_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    records_path = tmp_path / "records.jsonl"
    problem_source = tmp_path / "problems.jsonl"
    output_dir = tmp_path / "out"

    _write_jsonl(records_path, [_make_record("cli_problem")])
    _write_jsonl(
        problem_source,
        [
            {
                "id": "cli_problem",
                "description": "cli description",
                "public_tests": [{"input": "1", "output": "1"}],
                "tags": ["math"],
            }
        ],
    )

    exit_code = main(
        [
            "--input",
            str(records_path),
            "--problem-source",
            str(problem_source),
            "--output-dir",
            str(output_dir),
            "--prefix",
            "selector_dataset_cli",
        ]
    )

    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert len(list(output_dir.glob("selector_dataset_cli_audit_all_*.jsonl"))) == 1
    assert len(list(output_dir.glob("selector_dataset_cli_audit_all_*.csv"))) == 1
    assert len(list(output_dir.glob("selector_dataset_cli_trusted_train_subset_*.jsonl"))) == 1
    assert len(list(output_dir.glob("selector_dataset_cli_trusted_train_subset_*.csv"))) == 1
    assert "total_input_samples" in stdout
    assert "record_schema_version" in stdout
    assert "is_trusted_label" in stdout

    audit_csv = next(output_dir.glob("selector_dataset_cli_audit_all_*.csv"))
    with audit_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["cost_llm_calls"] == "6"
    assert rows[0]["candidate_family_pool_joined"] == "oracle.enumeration.n_nested_loops|oracle.dp.topdown"
