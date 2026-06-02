from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, TYPE_CHECKING

import src.events as events
from src.failure_bank import FailureBankService
from src.utils.cpp_execution import ExecutionLimits, run_program

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _emit_node_enter(node_name: str, phase: str) -> None:
    emitter = getattr(events, "emit_node_enter", None)
    if callable(emitter):
        emitter(node_name, phase)


def _trusted_tests(tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [test for test in tests if test.get("trust_tier", "advisory") == "trusted"]


def _run_trusted_suite(
    exe_path: Path,
    tests: List[Dict[str, Any]],
    run_program_fn=run_program,
) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for test in _trusted_tests(tests):
        retcode, stdout, stderr = run_program_fn(
            exe_path,
            input_text=test.get("input", ""),
            limits=ExecutionLimits.default_run(),
        )
        expected_output = str(test.get("expected_output", "") or "")
        if retcode != 0 or stdout.strip() != expected_output.strip():
            failures.append(
                {
                    "input_text": test.get("input", ""),
                    "expected_output": expected_output,
                    "actual_output": stdout,
                    "stderr": stderr,
                    "failure_type": "WA" if retcode == 0 else "RE",
                    "source_type": test.get("type", "trusted"),
                }
            )
    return failures


def _complexity_risk_flags(code: str, constraints: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    rendered_constraints = str(constraints or {}).lower()
    loop_count = len(re.findall(r"\bfor\b|\bwhile\b", code or ""))
    if loop_count >= 2 and any(
        token in rendered_constraints for token in ("1e5", "10^5", "100000", "2e5", "200000")
    ):
        flags.append("possible_quadratic_on_large_n")
    if "vector<vector" in (code or "") and any(
        token in rendered_constraints for token in ("1e5", "10^5", "100000")
    ):
        flags.append("possible_dense_memory")
    return flags


def _risk_pattern_flags(state: "SolvitaState") -> List[str]:
    flags: List[str] = []
    failure_bank_context = (state.get("failure_bank_context") or {})
    for pattern in failure_bank_context.get("matched_patterns", []) or []:
        flags.extend(str(item) for item in pattern.get("recommended_checks", []) or [])
    flags.extend(str(item) for item in failure_bank_context.get("anti_patterns", []) or [])
    deduped: List[str] = []
    seen = set()
    for flag in flags:
        if flag and flag not in seen:
            seen.add(flag)
            deduped.append(flag)
    return deduped


def _failure_bank_service_from_state(state: "SolvitaState") -> FailureBankService | None:
    config = (state.get("config") or {}).get("failure_bank", {}) or {}
    if config.get("enabled", True) is False:
        return None
    service = FailureBankService(config.get("data_dir", ""))
    service.initialize()
    return service


def verifier_phase_node(
    state: "SolvitaState",
    *,
    run_program_fn=run_program,
) -> Dict[str, Any]:
    _emit_node_enter("verifier_phase", "top")
    events.emit("phase_start", phase="verifier_phase", label="Independent Verification")

    tests = list((state.get("tests") or {}).get("generated_tests", []) or [])
    solution = state.get("solution") or {}
    problem = state.get("problem") or {}
    prior_verification = state.get("verification") or {}
    prior_open_case_ids = list(prior_verification.get("open_failure_case_ids", []) or [])

    exe_path_raw = solution.get("executable_path")
    code = str(solution.get("code", "") or "")
    constraints = problem.get("constraints", {}) or {}

    trusted_failures: List[Dict[str, Any]] = []
    if exe_path_raw and tests:
        trusted_failures = _run_trusted_suite(
            Path(exe_path_raw),
            tests,
            run_program_fn=run_program_fn,
        )

    if trusted_failures:
        problem = state.get("problem") or {}
        canonical = (problem.get("canonical") or {}) if isinstance(problem.get("canonical"), dict) else {}
        code_hash = hashlib.sha1(code.encode("utf-8")).hexdigest() if code else ""
        case_ids: List[str] = []
        service = _failure_bank_service_from_state(state)
        if service is not None:
            for failure in trusted_failures:
                case_ids.append(
                    service.record_failure_case(
                        {
                            "canonical_objective": str(canonical.get("objective", "") or problem.get("description", "") or ""),
                            "tags_level1": list(problem.get("tags_selected", []) or []),
                            "tags_level2": list(problem.get("tags_level2_selected", []) or []),
                            "constraint_bucket": str(problem.get("constraints", {}) or ""),
                            "phase_found": "verifier",
                            "failure_type": str(failure.get("failure_type", "WA") or "WA"),
                            "failure_subtype": "trusted_suite_failed",
                            "input_text": str(failure.get("input_text", "") or ""),
                            "expected_output": str(failure.get("expected_output", "") or ""),
                            "actual_output": str(failure.get("actual_output", "") or ""),
                            "checker_context": str(failure.get("stderr", "") or ""),
                            "trusted_level": "high",
                            "source_run_id": "",
                            "source_solution_hash": code_hash,
                            "explanation": "Verifier trusted suite mismatch.",
                            "minimized": True,
                        }
                    )
                )
        if prior_open_case_ids:
            seen_case_ids = set(case_ids)
            case_ids.extend(case_id for case_id in prior_open_case_ids if case_id not in seen_case_ids)
        verification = {
            "decision": "repair",
            "confidence": 1.0,
            "risk_flags": ["trusted_suite_failed"],
            "new_tests": [],
            "feedback_summary": "Trusted verification suite exposed a mismatch.",
            "trusted_failures": trusted_failures,
            "open_failure_case_ids": case_ids,
        }
        events.emit(
            "phase_done",
            phase="verifier_phase",
            label="Independent Verification",
            data={"decision": "repair"},
        )
        return {"verification": verification}

    risk_flags = _complexity_risk_flags(code, constraints)
    risk_flags.extend(_risk_pattern_flags(state))
    if risk_flags:
        verification = {
            "decision": "escalate_testgen",
            "confidence": 0.7,
            "risk_flags": risk_flags,
            "new_tests": [],
            "feedback_summary": "No trusted counterexample found, but risk remains too high for acceptance.",
            "trusted_failures": [],
            "open_failure_case_ids": prior_open_case_ids,
        }
        events.emit(
            "phase_done",
            phase="verifier_phase",
            label="Independent Verification",
            data={"decision": "escalate_testgen"},
        )
        return {"verification": verification}

    verification = {
        "decision": "accept",
        "confidence": 0.9,
        "risk_flags": [],
        "new_tests": [],
        "feedback_summary": "Trusted checks passed and no strong residual risk was detected.",
        "trusted_failures": [],
        "open_failure_case_ids": prior_open_case_ids,
    }
    events.emit(
        "phase_done",
        phase="verifier_phase",
        label="Independent Verification",
        data={"decision": "accept"},
    )
    return {"verification": verification}
