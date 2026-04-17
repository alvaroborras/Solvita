import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.state import create_initial_state
from src.nodes.best_solution import (
    enter_hack_phase_node,
    restore_best_solution_node,
    update_best_solution_node,
)


def test_create_initial_state_includes_best_solution_tracking_fields():
    state = create_initial_state({"description": "x", "public_tests": []}, {"max_iterations": 5})

    assert state["best_solution"] == {}
    assert state["best_tests"] == {}
    assert state["best_phase"] == "test"
    assert state["has_entered_hack_phase"] is False


def test_update_best_solution_node_records_pre_hack_best_solution():
    state = {
        "solution": {"code": "candidate", "version": 2, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 0.8, "passed_tests": 8, "total_tests": 10},
        "iteration": 1,
        "best_solution": {},
        "best_tests": {},
        "best_phase": "test",
        "has_entered_hack_phase": False,
    }

    patch = update_best_solution_node(state)

    assert patch["best_solution"]["code"] == "candidate"
    assert patch["best_phase"] == "test"


def test_enter_hack_phase_seeds_hack_best_from_current_solution():
    state = {
        "solution": {"code": "full-pass", "version": 4, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 1.0, "passed_tests": 10, "total_tests": 10},
        "iteration": 3,
        "best_solution": {"code": "old"},
        "best_tests": {"pass_rate": 0.8, "passed_tests": 8, "total_tests": 10},
        "best_phase": "test",
        "has_entered_hack_phase": False,
    }

    patch = enter_hack_phase_node(state)

    assert patch["has_entered_hack_phase"] is True
    assert patch["best_phase"] == "hack"
    assert patch["best_solution"]["code"] == "full-pass"


def test_update_best_solution_node_uses_hack_phase_scores_after_hack_entry():
    state = {
        "solution": {"code": "hack-candidate", "version": 5, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 0.95, "passed_tests": 19, "total_tests": 20},
        "iteration": 4,
        "best_solution": {"code": "hack-best", "version": 4, "compilation_success": True},
        "best_tests": {"pass_rate": 0.90, "passed_tests": 18, "total_tests": 20},
        "best_phase": "hack",
        "has_entered_hack_phase": True,
    }

    patch = update_best_solution_node(state)

    assert patch["best_solution"]["code"] == "hack-candidate"
    assert patch["best_phase"] == "hack"


def test_restore_best_solution_node_replaces_current_solution_on_max_iterations():
    state = {
        "status": "max_iterations",
        "solution": {"code": "last", "version": 6, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 0.3, "passed_tests": 3, "total_tests": 10},
        "best_solution": {"code": "best", "version": 4, "compilation_success": True, "compilation_errors": []},
        "best_tests": {"pass_rate": 1.0, "passed_tests": 10, "total_tests": 10, "recorded_iteration": 2, "phase": "test"},
    }

    patch = restore_best_solution_node(state)

    assert patch["solution"]["code"] == "best"
    assert patch["tests"]["pass_rate"] == 1.0


def test_pre_hack_best_solution_survives_later_regression():
    initial = {
        "solution": {"code": "good", "version": 1, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 1.0, "passed_tests": 10, "total_tests": 10},
        "iteration": 0,
        "best_solution": {},
        "best_tests": {},
        "best_phase": "test",
        "has_entered_hack_phase": False,
    }
    update_patch = update_best_solution_node(initial)

    regressed = {
        "status": "max_iterations",
        "solution": {"code": "bad", "version": 2, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 0.2, "passed_tests": 2, "total_tests": 10},
        "best_solution": update_patch["best_solution"],
        "best_tests": update_patch["best_tests"],
    }

    restore_patch = restore_best_solution_node(regressed)
    assert restore_patch["solution"]["code"] == "good"


def test_hack_phase_best_keeps_hack_entry_solution_when_later_hack_score_is_lower():
    pre_hack = {
        "solution": {"code": "pre", "version": 1, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 1.0, "passed_tests": 10, "total_tests": 10},
        "iteration": 0,
        "best_solution": {},
        "best_tests": {},
        "best_phase": "test",
        "has_entered_hack_phase": False,
    }
    pre_patch = update_best_solution_node(pre_hack)

    entering_hack = {
        **pre_hack,
        **pre_patch,
    }
    hack_seed = enter_hack_phase_node(entering_hack)

    hack_candidate = {
        "solution": {"code": "post", "version": 2, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 0.95, "passed_tests": 19, "total_tests": 20},
        "iteration": 1,
        "best_solution": hack_seed["best_solution"],
        "best_tests": hack_seed["best_tests"],
        "best_phase": hack_seed["best_phase"],
        "has_entered_hack_phase": True,
    }
    hack_best = update_best_solution_node(hack_candidate)

    final_state = {
        "status": "max_iterations",
        "solution": {"code": "last", "version": 3, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 0.6, "passed_tests": 12, "total_tests": 20},
        "best_solution": hack_best.get("best_solution", hack_seed["best_solution"]),
        "best_tests": hack_best.get("best_tests", hack_seed["best_tests"]),
    }
    restore_patch = restore_best_solution_node(final_state)
    assert restore_patch["solution"]["code"] == "pre"
