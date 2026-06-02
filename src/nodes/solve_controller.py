from __future__ import annotations

import hashlib
from typing import Any, Dict

import src.events as events
from src.failure_bank import FailureBankService
from src.nodes.routing import _hacker_enabled


HIGH_RISK_LEVEL1 = {"dp", "graphs", "math", "strings"}
HIGH_RISK_LEVEL2 = {
    "cyclic_convolution",
    "dsu_on_tree",
    "divide_and_conquer_dp",
    "implicit_segment_tree",
}


def _emit_node_enter(node_name: str, phase: str) -> None:
    emitter = getattr(events, "emit_node_enter", None)
    if callable(emitter):
        emitter(node_name, phase)


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


def _failure_bank_service_from_state(state: Dict[str, Any]) -> FailureBankService | None:
    config = (state.get("config") or {}).get("failure_bank", {}) or {}
    if config.get("enabled", True) is False:
        return None
    service = FailureBankService(config.get("data_dir", ""))
    service.initialize()
    return service


def pre_solve_controller_node(state: Dict[str, Any]) -> Dict[str, Any]:
    _emit_node_enter("pre_solve_controller", "top")

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
    _emit_node_enter("post_verify_controller", "top")

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
    open_case_ids = list(verification.get("open_failure_case_ids", []) or [])
    if not open_case_ids:
        return {"solve_policy": policy}

    service = _failure_bank_service_from_state(state)
    if service is not None:
        solution_code = str(((state.get("solution") or {}).get("code") or ""))
        service.record_repair_outcome(
            linked_case_ids=open_case_ids,
            repair_strategy="verifier_repair",
            repair_summary=str(
                verification.get("feedback_summary", "")
                or "Verifier-discovered failure closed by accepted solution."
            ),
            before_solution_hash="",
            after_solution_hash=hashlib.sha1(solution_code.encode("utf-8")).hexdigest()
            if solution_code
            else "",
            validated=True,
        )

    verification_patch = dict(verification)
    verification_patch["open_failure_case_ids"] = []
    return {"solve_policy": policy, "verification": verification_patch}
