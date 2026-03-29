from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def build_hacker_candidate_record(
    *,
    problem_id: str,
    route_used: str,
    hack_result: str,
    failure_type: str,
    generator_failure_kind: str,
    reward: float,
    validity_passed: bool,
    buggy_distinguished: bool,
    compile_failures: int,
) -> Dict[str, Any]:
    return {
        "problem_id": problem_id,
        "route_used": route_used,
        "hack_result": hack_result,
        "failure_type": failure_type,
        "generator_failure_kind": generator_failure_kind,
        "reward": reward,
        "validity_passed": validity_passed,
        "buggy_distinguished": buggy_distinguished,
        "compile_failures": compile_failures,
    }


def append_hacker_candidate_record(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
