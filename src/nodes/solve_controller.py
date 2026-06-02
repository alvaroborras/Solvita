from __future__ import annotations

from typing import Any, Dict

import src.events as events
from src.nodes.routing import _hacker_enabled


HIGH_RISK_LEVEL1 = {"dp", "graphs", "math", "strings"}
HIGH_RISK_LEVEL2 = {
    "cyclic_convolution",
    "dsu_on_tree",
    "divide_and_conquer_dp",
    "implicit_segment_tree",
}


def _risk_score(state: Dict[str, Any]) -> float:
    problem = state.get("problem", {}) or {}
    score = 0.0

    if float(problem.get("abstract_confidence", 0.0) or 0.0) < 0.75:
        score += 1.0

    tags_level1 = set(problem.get("tags_selected", []) or [])
    tags_level2 = set(problem.get("tags_level2_selected", []) or [])
    score += 0.5 * len(tags_level1.intersection(HIGH_RISK_LEVEL1))
    score += 1.0 * len(tags_level2.intersection(HIGH_RISK_LEVEL2))
    score += 1.0 * len(
        ((state.get("failure_bank_context", {}) or {}).get("matched_patterns", []) or [])
    )

    if not (problem.get("public_tests", []) or []):
        score += 0.5

    return score


def pre_solve_controller_node(state: Dict[str, Any]) -> Dict[str, Any]:
    events.emit_node_enter("pre_solve_controller", "top")

    score = _risk_score(state)
    config = state.get("config", {}) or {}
    benchmark_mode = bool(config.get("benchmark_output_dir"))
    solver_network_cfg = config.get("solver_network", {}) or {}
    hacker_enabled = _hacker_enabled(state)

    solve_policy = {
        "risk_score": score,
        "run_testgen_initially": score >= 2.5,
        "run_skill_plan": bool(solver_network_cfg.get("enabled")) and score >= 1.5,
        "initial_codegen_budget": 1 if score < 2.5 else 2,
        "verifier_mode": "strict" if score >= 2.5 else "standard",
        "allow_hacker": hacker_enabled and (not benchmark_mode) and score >= 3.0,
        "escalate_after_failures": 1,
        "generated_test_target_scale": 50 if score >= 2.5 else 0,
        "next_action": "",
    }

    return {
        "solve_policy": solve_policy,
        "execution_log": [
            f"Pre-solve controller: risk={score:.2f} run_testgen={solve_policy['run_testgen_initially']}"
        ],
    }


def post_verify_controller_node(state: Dict[str, Any]) -> Dict[str, Any]:
    events.emit_node_enter("post_verify_controller", "top")

    verification = state.get("verification", {}) or {}
    decision = str(verification.get("decision", "") or "")
    policy = dict(state.get("solve_policy", {}) or {})
    next_iteration = int(state.get("iteration", 0) or 0) + 1

    if decision == "repair":
        policy["next_action"] = "repair"
        return {
            "solve_policy": policy,
            "status": "pending",
            "iteration": next_iteration,
        }

    if decision == "escalate_testgen":
        policy["next_action"] = "escalate_testgen"
        return {
            "solve_policy": policy,
            "status": "pending",
            "iteration": next_iteration,
            "current_phase": "TESTGEN",
        }

    policy["next_action"] = (
        "accept_hack"
        if policy.get("allow_hacker", False) and _hacker_enabled(state)
        else "accept_end"
    )
    return {"solve_policy": policy}
