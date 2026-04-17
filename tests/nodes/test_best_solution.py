import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.best_solution import (
    is_better_candidate,
    update_best_solution_snapshot,
)


def test_is_better_candidate_prefers_higher_pass_rate():
    current_solution = {"code": "new", "version": 2, "compilation_success": True}
    current_tests = {"pass_rate": 0.9, "passed_tests": 9, "total_tests": 10}
    best_solution = {"code": "old", "version": 1, "compilation_success": True}
    best_tests = {"pass_rate": 0.8, "passed_tests": 8, "total_tests": 10}

    assert is_better_candidate(current_solution, current_tests, best_solution, best_tests) is True


def test_is_better_candidate_keeps_existing_best_on_exact_tie():
    current_solution = {"code": "new", "version": 2, "compilation_success": True}
    current_tests = {"pass_rate": 1.0, "passed_tests": 10, "total_tests": 10}
    best_solution = {"code": "old", "version": 1, "compilation_success": True}
    best_tests = {"pass_rate": 1.0, "passed_tests": 10, "total_tests": 10}

    assert is_better_candidate(current_solution, current_tests, best_solution, best_tests) is False


def test_update_best_solution_snapshot_records_phase_and_iteration():
    state = {
        "solution": {"code": "best", "version": 3, "compilation_success": True, "compilation_errors": []},
        "tests": {"pass_rate": 1.0, "passed_tests": 10, "total_tests": 10},
        "iteration": 2,
        "best_solution": {},
        "best_tests": {},
        "best_phase": "test",
    }

    patch = update_best_solution_snapshot(state, phase="test")

    assert patch["best_solution"]["code"] == "best"
    assert patch["best_tests"]["pass_rate"] == 1.0
    assert patch["best_tests"]["recorded_iteration"] == 2
    assert patch["best_phase"] == "test"
