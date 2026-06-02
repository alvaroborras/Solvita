"""Pass@1 workflow state scaffolding defaults."""

import sys
from pathlib import Path
from typing import get_args, get_origin

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import (
    FailureBankContextData,
    SolvePolicyData,
    SolvitaState,
    TestData as StateTestData,
    VerificationData,
    create_initial_state,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pass1_state_schema_declares_new_contracts():
    solve_policy_annotation = SolvitaState.__annotations__["solve_policy"]
    verification_annotation = SolvitaState.__annotations__["verification"]
    failure_bank_annotation = SolvitaState.__annotations__["failure_bank_context"]

    assert get_args(solve_policy_annotation)[0] is SolvePolicyData
    assert set(SolvePolicyData.__annotations__) == {
        "risk_score",
        "run_testgen_initially",
        "run_skill_plan",
        "initial_codegen_budget",
        "verifier_mode",
        "allow_hacker",
        "escalate_after_failures",
        "generated_test_target_scale",
        "next_action",
    }

    assert get_args(verification_annotation)[0] is VerificationData
    assert set(VerificationData.__annotations__) == {
        "decision",
        "confidence",
        "risk_flags",
        "new_tests",
        "feedback_summary",
        "trusted_failures",
        "open_failure_case_ids",
    }

    assert get_args(failure_bank_annotation)[0] is FailureBankContextData
    assert set(FailureBankContextData.__annotations__) == {
        "matched_patterns",
        "retrieved_counterexamples",
        "anti_patterns",
        "repair_summaries",
        "source_case_ids",
    }

    assert "full_testgen_completed" in StateTestData.__annotations__
    assert StateTestData.__annotations__["full_testgen_completed"] is bool
    assert "full_testgen_completed" in StateTestData.__optional_keys__

    trust_tiers_annotation = StateTestData.__annotations__["trust_tiers"]
    assert "trust_tiers" in StateTestData.__annotations__
    assert "trust_tiers" in StateTestData.__optional_keys__
    assert get_origin(trust_tiers_annotation) is dict
    assert get_args(trust_tiers_annotation) == (str, int)


def test_initial_state_contains_pass1_fields():
    state = create_initial_state(
        raw_problem={
            "description": "Example",
            "time_limit": 2000,
            "space_limit": 256,
            "public_tests": [],
        },
        config={},
    )

    assert state["solve_policy"] == {
        "risk_score": 0.0,
        "run_testgen_initially": False,
        "run_skill_plan": False,
        "initial_codegen_budget": 1,
        "verifier_mode": "standard",
        "allow_hacker": False,
        "escalate_after_failures": 1,
        "generated_test_target_scale": 0,
        "next_action": "",
    }
    assert state["verification"] == {
        "decision": "",
        "confidence": 0.0,
        "risk_flags": [],
        "new_tests": [],
        "feedback_summary": "",
        "trusted_failures": [],
        "open_failure_case_ids": [],
    }
    assert state["failure_bank_context"] == {
        "matched_patterns": [],
        "retrieved_counterexamples": [],
        "anti_patterns": [],
        "repair_summaries": [],
        "source_case_ids": [],
    }
    assert state["tests"]["full_testgen_completed"] is False
    assert state["tests"]["trust_tiers"] == {}
    assert state["current_phase"] == "ABSTRACT"
    assert "solver_network" in state["config"]
    assert "trainable_memory" in state["config"]


def test_runtime_config_applies_failure_bank_defaults():
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )

    failure_bank_cfg = state["config"]["failure_bank"]
    assert "failure_bank" in state["config"]
    assert failure_bank_cfg["enabled"] is True
    assert failure_bank_cfg["lookup_limit"] == 3
    assert failure_bank_cfg["data_dir"] == str((REPO_ROOT / "artifacts" / "failure_bank").resolve())
    assert "solver_network" in state["config"]
    assert "trainable_memory" in state["config"]


def test_runtime_config_merges_failure_bank_lookup_limit_override():
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={"failure_bank": {"lookup_limit": 7}},
    )

    failure_bank_cfg = state["config"]["failure_bank"]
    assert failure_bank_cfg["enabled"] is True
    assert failure_bank_cfg["lookup_limit"] == 7
    assert failure_bank_cfg["data_dir"] == str((REPO_ROOT / "artifacts" / "failure_bank").resolve())
    assert "solver_network" in state["config"]
    assert "trainable_memory" in state["config"]
