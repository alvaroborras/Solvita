from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_oracle_event_payload(
    *,
    problem_hash: str,
    trainability_class: str,
    candidate_family_pool: List[str],
    selected_family_ids: List[str],
    selector_version: str,
    propensity: float,
    certification_route: str,
    verifier_provenance: Optional[Dict[str, Any]],
    decision: str,
    artifact_kind: str,
    cost: Dict[str, Any],
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "problem_hash": problem_hash,
        "trainability_class": trainability_class,
        "candidate_family_pool": candidate_family_pool,
        "selected_family_ids": selected_family_ids,
        "selector_version": selector_version,
        "propensity": propensity,
        "certification_route": certification_route,
        "verifier_provenance": verifier_provenance,
        "decision": decision,
        "artifact_kind": artifact_kind,
        "cost": cost,
        "evidence": evidence or {},
    }
