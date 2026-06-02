"""Verifier phase decision tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import create_initial_state
from src.nodes.verifier_phase import verifier_phase_node


def test_verifier_repairs_on_trusted_test_failure(tmp_path: Path):
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )
    state["solution"]["executable_path"] = str(tmp_path / "dummy.exe")
    state["tests"]["generated_tests"] = [
        {
            "input": "1\n",
            "expected_output": "2\n",
            "trust_tier": "trusted",
            "type": "public",
            "description": "Public test",
        }
    ]
    state["tests"]["ready"] = True

    update = verifier_phase_node(
        state,
        run_program_fn=lambda *_args, **_kwargs: (0, "1\n", ""),
    )

    assert update["verification"]["decision"] == "repair"
    assert "trusted_suite_failed" in update["verification"]["risk_flags"]
    assert update["verification"]["trusted_failures"][0]["expected_output"] == "2\n"


def test_verifier_escalates_when_complexity_risk_is_high(tmp_path: Path):
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )
    state["solution"]["code"] = "int main(){ for(int i=0;i<n;i++) for(int j=0;j<n;j++){} }"
    state["problem"]["constraints"] = {"n": "2e5"}
    state["solution"]["executable_path"] = str(tmp_path / "dummy.exe")
    state["tests"]["generated_tests"] = []
    state["tests"]["ready"] = True

    update = verifier_phase_node(state)

    assert update["verification"]["decision"] == "escalate_testgen"
    assert "possible_quadratic_on_large_n" in update["verification"]["risk_flags"]


def test_verifier_accepts_low_risk_candidate(tmp_path: Path):
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )
    state["solution"]["code"] = "int main(){return 0;}"
    state["solution"]["executable_path"] = str(tmp_path / "dummy.exe")
    state["tests"]["generated_tests"] = []
    state["tests"]["ready"] = True

    update = verifier_phase_node(
        state,
        run_program_fn=lambda *_args, **_kwargs: (0, "", ""),
    )

    assert update["verification"]["decision"] == "accept"
    assert update["verification"]["confidence"] > 0.0
