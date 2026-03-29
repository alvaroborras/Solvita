from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def build_candidate_record(
    *,
    problem_id: str,
    trainability_class: str,
    candidate_family_pool: List[str],
    selected_family_id: str,
    fallback_family_id: str = "",
    compile_success: bool,
    public_self_check_pass: bool,
    probe_pack_pass: bool,
    route: str,
    artifact_kind: str,
    decision: str,
    certified_count: int = 0,
    certified_target_count: int = 0,
    cert_ratio: float = 0.0,
    reward: float = 0.0,
    reward_reason: str = "",
    failure_stage: str = "",
    failure_subtype: str = "",
    checker_fallback_used: bool = False,
    solver_attempt_count: int = 0,
    selected_template_name: str = "",
    prompt_char_stats: Dict[str, int] | None = None,
    compact_retry_count: int = 0,
    verifier_provenance: Dict[str, Any] | None = None,
    cost: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "problem_id": problem_id,
        "trainability_class": trainability_class,
        "candidate_family_pool": candidate_family_pool,
        "selected_family_id": selected_family_id,
        "fallback_family_id": fallback_family_id,
        "compile_success": compile_success,
        "public_self_check_pass": public_self_check_pass,
        "probe_pack_pass": probe_pack_pass,
        "route": route,
        "artifact_kind": artifact_kind,
        "decision": decision,
        "certified_count": certified_count,
        "certified_target_count": certified_target_count,
        "cert_ratio": cert_ratio,
        "reward": reward,
        "reward_reason": reward_reason,
        "failure_stage": failure_stage,
        "failure_subtype": failure_subtype,
        "checker_fallback_used": checker_fallback_used,
        "solver_attempt_count": solver_attempt_count,
        "selected_template_name": selected_template_name,
        "prompt_char_stats": prompt_char_stats or {},
        "compact_retry_count": compact_retry_count,
        "verifier_provenance": verifier_provenance,
        "cost": cost or {},
    }


def append_candidate_record(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
