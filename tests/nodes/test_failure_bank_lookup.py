"""Failure-bank lookup node reads configured SQLite context into state."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.failure_bank.service import FailureBankService
from src.graph.state import create_initial_state
from src.nodes import failure_bank_lookup_node


def test_failure_bank_lookup_node_reads_context_from_configured_store(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    service.record_failure_case(
        {
            "canonical_objective": "Count paths",
            "tags_level1": ["graphs"],
            "tags_level2": [],
            "constraint_bucket": "n<=1e5",
            "phase_found": "hacker",
            "failure_type": "TLE",
            "failure_subtype": "quadratic_paths",
            "input_text": "5 4\n1 2\n2 3\n3 4\n4 5\n",
            "expected_output": "4\n",
            "actual_output": "timeout",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-2",
            "source_solution_hash": "hash-2",
            "explanation": "Nested loop over all pairs.",
            "minimized": True,
        }
    )

    state = create_initial_state(
        raw_problem={"description": "Count paths", "public_tests": []},
        config={"failure_bank": {"data_dir": str(tmp_path), "lookup_limit": 2}},
    )
    state["problem"]["canonical"] = {"objective": "Count paths"}
    state["problem"]["tags_selected"] = ["graphs"]

    update = failure_bank_lookup_node(state)

    assert update["failure_bank_context"]["retrieved_counterexamples"][0]["failure_subtype"] == "quadratic_paths"
    assert update["execution_log"] == ["Failure bank lookup: patterns=0 counterexamples=1"]


def test_failure_bank_lookup_node_returns_empty_context_when_disabled(tmp_path: Path):
    state = create_initial_state(
        raw_problem={"description": "Count paths", "public_tests": []},
        config={"failure_bank": {"enabled": False, "data_dir": str(tmp_path)}},
    )
    state["problem"]["canonical"] = {"objective": "Count paths"}
    state["problem"]["tags_selected"] = ["graphs"]

    update = failure_bank_lookup_node(state)

    assert update["failure_bank_context"] == {
        "matched_patterns": [],
        "retrieved_counterexamples": [],
        "anti_patterns": [],
        "repair_summaries": [],
        "source_case_ids": [],
    }
    assert update["execution_log"] == ["Failure bank lookup: disabled"]


def test_failure_bank_lookup_node_falls_back_to_problem_description_and_level2_tags(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    service.record_risk_pattern(
        {
            "pattern_id": "pattern.graph.level2",
            "title": "Graph level2 pattern",
            "applicable_tags": ["dag_longest_path"],
            "trigger_features": ["dag"],
            "anti_pattern_text": "Check DAG edge directions carefully.",
            "recommended_checks": ["dag_direction"],
            "evidence_case_ids": [],
        }
    )
    service.record_failure_case(
        {
            "canonical_objective": "Fallback objective from description",
            "tags_level1": [],
            "tags_level2": ["dag_longest_path"],
            "constraint_bucket": "n<=1e5",
            "phase_found": "verifier",
            "failure_type": "WA",
            "failure_subtype": "direction_bug",
            "input_text": "3 2\n1 2\n2 3\n",
            "expected_output": "2\n",
            "actual_output": "1\n",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-4",
            "source_solution_hash": "hash-4",
            "explanation": "Edge direction mishandled.",
            "minimized": True,
        }
    )

    state = create_initial_state(
        raw_problem={"description": "Fallback objective from description", "public_tests": []},
        config={"failure_bank": {"data_dir": str(tmp_path), "lookup_limit": 2}},
    )
    state["problem"]["description"] = "Fallback objective from description"
    state["problem"]["canonical"] = {}
    state["problem"]["tags_selected"] = []
    state["problem"]["tags_level2_selected"] = ["dag_longest_path"]

    update = failure_bank_lookup_node(state)

    assert update["failure_bank_context"]["matched_patterns"][0]["pattern_id"] == "pattern.graph.level2"
    assert update["failure_bank_context"]["retrieved_counterexamples"][0]["failure_subtype"] == "direction_bug"


def test_failure_bank_lookup_node_blank_data_dir_is_safe_and_non_polluting(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = create_initial_state(
        raw_problem={"description": "Count paths", "public_tests": []},
        config={"failure_bank": {"data_dir": "", "lookup_limit": 2}},
    )
    state["problem"]["canonical"] = {"objective": "Count paths"}
    state["problem"]["tags_selected"] = ["graphs"]

    update = failure_bank_lookup_node(state)

    assert update["failure_bank_context"] == {
        "matched_patterns": [],
        "retrieved_counterexamples": [],
        "anti_patterns": [],
        "repair_summaries": [],
        "source_case_ids": [],
    }
    assert not (tmp_path / "failure_bank.db").exists()
