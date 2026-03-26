from __future__ import annotations

from typing import Any, Dict, Optional

from src.oracle.types import AcceptedArtifactKind, OracleRoute


def build_accepted_artifact(
    *,
    route: OracleRoute,
    input_text: str,
    output_text: str,
    verifier_provenance: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if route is OracleRoute.EXACT_SINGLE_ANSWER:
        return {
            "kind": AcceptedArtifactKind.EXPECTED_OUTPUT.value,
            "input": input_text,
            "expected_output": output_text,
            "evidence": evidence or {},
        }
    if route is OracleRoute.TRUSTED_CHECKER_BACKED_MULTI:
        if verifier_provenance is None:
            raise ValueError("trusted checker route requires verifier provenance")
        return {
            "kind": AcceptedArtifactKind.CHECKER_BUNDLE.value,
            "input": input_text,
            "output": output_text,
            "verifier_provenance": verifier_provenance,
            "evidence": evidence or {},
        }
    raise ValueError(f"unsupported route: {route}")
