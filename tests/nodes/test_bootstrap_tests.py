"""Bootstrap tests node builds a trusted seed suite before full testgen."""

import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_bootstrap_tests_preserves_existing_test_fields_and_emits_node_enter(monkeypatch):
    import src.nodes.bootstrap_tests as bt

    calls = []
    fake_events = SimpleNamespace(
        emit_node_enter=lambda name, lane: calls.append((name, lane)),
    )
    monkeypatch.setattr(bt, "events", fake_events, raising=False)

    state = create_initial_state(
        raw_problem={
            "description": "Example",
            "public_tests": [{"input": "1\n", "output": "1\n"}],
        },
        config={},
    )
    state["tests"]["oracle_status"] = "failed"
    state["tests"]["checker_exe"] = "/tmp/checker.exe"
    state["tests"]["validator_exe"] = "/tmp/validator.exe"

    update = bootstrap_tests_node(state)

    assert calls == [("bootstrap_tests", "top")]
    assert update["tests"]["oracle_status"] == "failed"
    assert update["tests"]["checker_exe"] == "/tmp/checker.exe"
    assert update["tests"]["validator_exe"] == "/tmp/validator.exe"
    assert update["tests"]["full_testgen_completed"] is False
