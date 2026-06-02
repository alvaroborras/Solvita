import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import create_initial_state
from src.nodes.solve_controller import (
    post_verify_controller_node,
    pre_solve_controller_node,
)


def test_pre_solve_controller_skips_full_testgen_for_low_risk_problem():
    state = create_initial_state(
        raw_problem={
            "description": "Add two numbers",
            "public_tests": [{"input": "1 2\n", "output": "3\n"}],
        },
        config={},
    )
    state["problem"]["canonical"] = {"objective": "Add two integers"}
    state["problem"]["abstract_confidence"] = 0.95
    state["problem"]["tags_selected"] = ["implementation"]

    update = pre_solve_controller_node(state)

    assert update["solve_policy"]["run_testgen_initially"] is False
    assert update["solve_policy"]["allow_hacker"] is False


def test_pre_solve_controller_escalates_high_risk_cyclic_problem():
    state = create_initial_state(
        raw_problem={"description": "Count cyclic segments", "public_tests": []},
        config={"solver_network": {"enabled": True}},
    )
    state["problem"]["canonical"] = {"objective": "Count cyclic segments"}
    state["problem"]["abstract_confidence"] = 0.60
    state["problem"]["tags_selected"] = ["dp", "math"]
    state["problem"]["tags_level2_selected"] = ["cyclic_convolution"]
    state["failure_bank_context"]["matched_patterns"] = [{"pattern_id": "pattern.cyclic.counting"}]

    update = pre_solve_controller_node(state)

    assert update["solve_policy"]["run_testgen_initially"] is True
    assert update["solve_policy"]["verifier_mode"] == "strict"


def test_post_verify_controller_requests_repair_and_bumps_iteration():
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )
    state["iteration"] = 1
    state["verification"] = {
        "decision": "repair",
        "confidence": 1.0,
        "risk_flags": ["trusted_suite_failed"],
        "new_tests": [],
        "feedback_summary": "",
        "trusted_failures": [],
        "open_failure_case_ids": [],
    }

    update = post_verify_controller_node(state)

    assert update["solve_policy"]["next_action"] == "repair"
    assert update["iteration"] == 2
    assert update["status"] == "pending"
