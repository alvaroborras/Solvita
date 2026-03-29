from __future__ import annotations

from typing import Any, Dict


def build_hacker_event_payload(
    *,
    route_used: str,
    hack_result: str,
    failure_type: str,
    generator_failure_kind: str,
    compile_failures: int,
    validity_passed: bool,
    buggy_distinguished: bool,
    reward: float,
) -> Dict[str, Any]:
    return {
        "route_used": route_used,
        "hack_result": hack_result,
        "failure_type": failure_type,
        "generator_failure_kind": generator_failure_kind,
        "compile_failures": compile_failures,
        "validity_passed": validity_passed,
        "buggy_distinguished": buggy_distinguished,
        "reward": reward,
    }
