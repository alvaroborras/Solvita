"""Failure bank service persists and retrieves structured context."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.failure_bank import FailureBankService


def test_failure_bank_service_stores_and_retrieves_context(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    service.record_risk_pattern(
        {
            "pattern_id": "pattern.cyclic.counting",
            "title": "Cyclic counting over-count",
            "applicable_tags": ["dp", "math"],
            "trigger_features": ["cyclic", "counting"],
            "anti_pattern_text": "Do not linearize cyclic set semantics without proof.",
            "recommended_checks": ["full_cycle_dedup", "wraparound_cases"],
            "evidence_case_ids": [],
        }
    )
    service.record_failure_case(
        {
            "canonical_objective": "Count valid cyclic segments",
            "tags_level1": ["dp", "math"],
            "tags_level2": ["cyclic_convolution"],
            "constraint_bucket": "n<=2e5",
            "phase_found": "verifier",
            "failure_type": "WA",
            "failure_subtype": "cyclic_overcount",
            "input_text": "1 3 2\n1\n",
            "expected_output": "1\n",
            "actual_output": "3\n",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-1",
            "source_solution_hash": "hash-1",
            "explanation": "Full cycle counted multiple times.",
            "minimized": True,
        }
    )

    context = service.lookup_context(
        canonical_objective="Count valid cyclic segments",
        tags_level1=["dp", "math"],
        tags_level2=["cyclic_convolution"],
        lookup_limit=3,
    )

    assert context["matched_patterns"][0]["pattern_id"] == "pattern.cyclic.counting"
    assert context["retrieved_counterexamples"][0]["failure_subtype"] == "cyclic_overcount"
    assert "Do not linearize cyclic set semantics without proof." in context["anti_patterns"]


def test_failure_bank_service_lookup_context_accepts_positional_arguments(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    service.record_failure_case(
        {
            "canonical_objective": "Count paths",
            "tags_level1": ["graphs"],
            "tags_level2": ["dag_longest_path"],
            "constraint_bucket": "n<=1e5",
            "phase_found": "verifier",
            "failure_type": "WA",
            "failure_subtype": "dag_off_by_one",
            "input_text": "3 2\n1 2\n2 3\n",
            "expected_output": "2\n",
            "actual_output": "1\n",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-3",
            "source_solution_hash": "hash-3",
            "explanation": "Missed one edge in path count.",
            "minimized": True,
        }
    )

    context = service.lookup_context("Count paths", ["graphs"], ["dag_longest_path"], 1)

    assert context["retrieved_counterexamples"][0]["failure_subtype"] == "dag_off_by_one"


def test_failure_bank_service_persists_distinct_observations_that_previously_collided(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()

    payload = {
        "canonical_objective": "Count paths",
        "tags_level1": ["graphs"],
        "tags_level2": [],
        "constraint_bucket": "n<=1e5",
        "phase_found": "verifier",
        "failure_type": "WA",
        "input_text": "4 3\n1 2\n2 3\n3 4\n",
        "actual_output": "7\n",
        "checker_context": "",
        "trusted_level": "high",
        "minimized": True,
    }
    service.record_failure_case(
        {
            **payload,
            "expected_output": "4\n",
            "failure_subtype": "missed_terminal_node",
            "source_run_id": "run-a",
            "source_solution_hash": "hash-a",
            "explanation": "Missed the terminal path.",
        }
    )
    service.record_failure_case(
        {
            **payload,
            "expected_output": "5\n",
            "failure_subtype": "double_counted_branch",
            "source_run_id": "run-b",
            "source_solution_hash": "hash-b",
            "explanation": "Double-counted a branch.",
        }
    )

    context = service.lookup_context("Count paths", ["graphs"], [], 10)

    assert len(context["retrieved_counterexamples"]) == 2
    assert {item["failure_subtype"] for item in context["retrieved_counterexamples"]} == {
        "missed_terminal_node",
        "double_counted_branch",
    }


def test_failure_bank_service_ranks_exact_objective_before_tag_only_matches(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    service.record_failure_case(
        {
            "canonical_objective": "Exact path objective",
            "tags_level1": ["graphs"],
            "tags_level2": [],
            "constraint_bucket": "n<=1e5",
            "phase_found": "verifier",
            "failure_type": "WA",
            "failure_subtype": "exact_match",
            "input_text": "3 2\n1 2\n2 3\n",
            "expected_output": "2\n",
            "actual_output": "1\n",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-exact",
            "source_solution_hash": "hash-exact",
            "explanation": "Exact objective case.",
            "minimized": True,
        }
    )
    service.record_failure_case(
        {
            "canonical_objective": "Different graph objective",
            "tags_level1": ["graphs"],
            "tags_level2": [],
            "constraint_bucket": "n<=1e5",
            "phase_found": "hacker",
            "failure_type": "TLE",
            "failure_subtype": "tag_only_newer",
            "input_text": "5 4\n1 2\n2 3\n3 4\n4 5\n",
            "expected_output": "4\n",
            "actual_output": "timeout",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-tag",
            "source_solution_hash": "hash-tag",
            "explanation": "Newer generic tag-only case.",
            "minimized": True,
        }
    )

    context = service.lookup_context("Exact path objective", ["graphs"], [], 2)

    assert [item["failure_subtype"] for item in context["retrieved_counterexamples"]] == [
        "exact_match",
        "tag_only_newer",
    ]


def test_failure_bank_records_repair_outcomes(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()

    repair_id = service.record_repair_outcome(
        linked_case_ids=["case-1"],
        repair_strategy="verifier_repair",
        repair_summary="Switched from quadratic scan to prefix sums.",
        before_solution_hash="before",
        after_solution_hash="after",
        validated=True,
    )

    outcomes = service.list_repair_outcomes()

    assert repair_id
    assert outcomes == [
        {
            "repair_id": repair_id,
            "linked_case_ids": ["case-1"],
            "repair_strategy": "verifier_repair",
            "repair_summary": "Switched from quadratic scan to prefix sums.",
            "before_solution_hash": "before",
            "after_solution_hash": "after",
            "validated": True,
        }
    ]


def test_failure_bank_lookup_surfaces_repair_summaries_for_retrieved_cases(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    case_id = service.record_failure_case(
        {
            "canonical_objective": "Count cyclic segments",
            "tags_level1": ["dp"],
            "tags_level2": ["cyclic_convolution"],
            "constraint_bucket": "n<=2e5",
            "phase_found": "verifier",
            "failure_type": "WA",
            "failure_subtype": "trusted_suite_failed",
            "input_text": "3\n1 2 3\n",
            "expected_output": "2\n",
            "actual_output": "3\n",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-4",
            "source_solution_hash": "hash-4",
            "explanation": "Verifier mismatch.",
            "minimized": True,
        }
    )
    service.record_repair_outcome(
        linked_case_ids=[case_id],
        repair_strategy="verifier_repair",
        repair_summary="Switched to prefix sums.",
        before_solution_hash="before-hash",
        after_solution_hash="after-hash",
        validated=True,
    )

    context = service.lookup_context(
        canonical_objective="Count cyclic segments",
        tags_level1=["dp"],
        tags_level2=["cyclic_convolution"],
        lookup_limit=3,
    )

    assert context["repair_summaries"] == [
        {
            "repair_id": context["repair_summaries"][0]["repair_id"],
            "linked_case_ids": [case_id],
            "repair_strategy": "verifier_repair",
            "repair_summary": "Switched to prefix sums.",
            "before_solution_hash": "before-hash",
            "after_solution_hash": "after-hash",
            "validated": True,
        }
    ]
