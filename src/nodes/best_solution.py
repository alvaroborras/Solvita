from __future__ import annotations

from typing import Any, Dict


def is_better_candidate(
    current_solution: Dict[str, Any],
    current_tests: Dict[str, Any],
    best_solution: Dict[str, Any],
    best_tests: Dict[str, Any],
) -> bool:
    if not best_solution:
        return True

    current_compile = bool(current_solution.get("compilation_success", False))
    best_compile = bool(best_solution.get("compilation_success", False))
    if current_compile != best_compile:
        return current_compile and not best_compile

    current_pass_rate = float(current_tests.get("pass_rate", 0.0) or 0.0)
    best_pass_rate = float(best_tests.get("pass_rate", 0.0) or 0.0)
    if current_pass_rate != best_pass_rate:
        return current_pass_rate > best_pass_rate

    current_passed = int(current_tests.get("passed_tests", 0) or 0)
    best_passed = int(best_tests.get("passed_tests", 0) or 0)
    if current_passed != best_passed:
        return current_passed > best_passed

    return False


def update_best_solution_snapshot(state: Dict[str, Any], *, phase: str) -> Dict[str, Any]:
    solution = dict(state.get("solution", {}))
    tests = dict(state.get("tests", {}))
    iteration = int(state.get("iteration", 0) or 0)

    best_solution = {
        "code": solution.get("code", ""),
        "version": solution.get("version", 0),
        "compilation_success": solution.get("compilation_success", False),
        "compilation_errors": list(solution.get("compilation_errors", [])),
        "memory_item_ids": list(solution.get("memory_item_ids", [])),
        "diagnostic_mode": solution.get("diagnostic_mode", False),
    }
    best_tests = {
        "pass_rate": float(tests.get("pass_rate", 0.0) or 0.0),
        "passed_tests": int(tests.get("passed_tests", 0) or 0),
        "total_tests": int(tests.get("total_tests", 0) or 0),
        "recorded_iteration": iteration,
        "phase": phase,
    }
    return {
        "best_solution": best_solution,
        "best_tests": best_tests,
        "best_phase": phase,
    }


def update_best_solution_node(state: Dict[str, Any]) -> Dict[str, Any]:
    phase = "hack" if state.get("has_entered_hack_phase", False) else "test"
    current_solution = dict(state.get("solution", {}))
    current_tests = dict(state.get("tests", {}))
    best_solution = dict(state.get("best_solution", {}))
    best_tests = dict(state.get("best_tests", {}))
    best_phase = str(state.get("best_phase", phase) or phase)

    if best_solution and best_phase != phase:
        return {}

    if is_better_candidate(current_solution, current_tests, best_solution, best_tests):
        patch = update_best_solution_snapshot(state, phase=phase)
        patch["execution_log"] = [
            f"Best solution updated in {phase} phase: pass={current_tests.get('pass_rate', 0.0):.1%}"
        ]
        return patch
    return {}


def enter_hack_phase_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("has_entered_hack_phase", False):
        return {}

    patch = update_best_solution_snapshot(state, phase="hack")
    patch["has_entered_hack_phase"] = True
    patch["execution_log"] = ["Entering hack phase: seeded hack-phase best solution"]
    return patch


def restore_best_solution_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("status") != "max_iterations":
        return {}

    best_solution = dict(state.get("best_solution", {}))
    if not best_solution:
        return {}

    best_tests = dict(state.get("best_tests", {}))
    patched_tests = dict(state.get("tests", {}))
    if best_tests:
        patched_tests.update({
            "pass_rate": best_tests.get("pass_rate", patched_tests.get("pass_rate", 0.0)),
            "passed_tests": best_tests.get("passed_tests", patched_tests.get("passed_tests", 0)),
            "total_tests": best_tests.get("total_tests", patched_tests.get("total_tests", 0)),
        })

    return {
        "solution": best_solution,
        "tests": patched_tests,
        "execution_log": [
            f"Restored best solution from {best_tests.get('phase', 'unknown')} phase at iteration {best_tests.get('recorded_iteration', '?')}"
        ],
    }
