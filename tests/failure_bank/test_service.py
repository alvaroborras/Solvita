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
