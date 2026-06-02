"""Pass@1 workflow state scaffolding defaults."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import create_initial_state


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


def test_runtime_config_merges_failure_bank_defaults():
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={"failure_bank": {"lookup_limit": 7}},
    )

    failure_bank_cfg = state["config"]["failure_bank"]
    assert failure_bank_cfg["enabled"] is True
    assert failure_bank_cfg["lookup_limit"] == 7
    assert failure_bank_cfg["data_dir"].endswith("artifacts/failure_bank")
    assert "solver_network" in state["config"]
    assert "trainable_memory" in state["config"]
