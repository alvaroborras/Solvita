"""Bootstrap tests node builds a trusted seed suite before full testgen."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import create_initial_state
from src.nodes.bootstrap_tests import bootstrap_tests_node


def test_bootstrap_tests_create_trusted_suite_from_public_tests():
    state = create_initial_state(
        raw_problem={
            "description": "Example",
            "public_tests": [{"input": "1\n", "output": "1\n"}],
        },
        config={},
    )

    update = bootstrap_tests_node(state)
    tests = update["tests"]

    assert tests["ready"] is True
    assert tests["full_testgen_completed"] is False
    assert tests["trust_tiers"] == {"trusted": 1}
    assert tests["generated_tests"][0]["trust_tier"] == "trusted"
    assert tests["generated_tests"][0]["type"] == "public"


def test_bootstrap_tests_add_failure_bank_counterexamples_as_trusted():
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )
    state["failure_bank_context"]["retrieved_counterexamples"] = [
        {
            "input_text": "2\n1 2\n",
            "expected_output": "3\n",
            "failure_type": "WA",
        }
    ]

    update = bootstrap_tests_node(state)

    assert update["tests"]["trust_tiers"] == {"trusted": 1}
    assert update["tests"]["generated_tests"][0]["type"] == "failure_bank"
    assert update["tests"]["generated_tests"][0]["trust_tier"] == "trusted"
