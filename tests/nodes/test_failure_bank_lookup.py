"""Failure-bank lookup node reads configured SQLite context into state."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.failure_bank.service import FailureBankService
from src.graph.state import create_initial_state
from src.nodes.failure_bank_lookup import failure_bank_lookup_node


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
