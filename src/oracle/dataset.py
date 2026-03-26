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
    compile_success: bool,
    public_self_check_pass: bool,
    probe_pack_pass: bool,
    route: str,
    artifact_kind: str,
    decision: str,
    verifier_provenance: Dict[str, Any] | None = None,
    cost: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "problem_id": problem_id,
        "trainability_class": trainability_class,
        "candidate_family_pool": candidate_family_pool,
        "selected_family_id": selected_family_id,
        "compile_success": compile_success,
        "public_self_check_pass": public_self_check_pass,
        "probe_pack_pass": probe_pack_pass,
        "route": route,
        "artifact_kind": artifact_kind,
        "decision": decision,
        "verifier_provenance": verifier_provenance,
        "cost": cost or {},
    }


def append_candidate_record(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
