from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class OracleRoute(str, Enum):
    EXACT_SINGLE_ANSWER = "exact_single_answer"
    TRUSTED_CHECKER_BACKED_MULTI = "trusted_checker_backed_multi"
    UNSUPPORTED = "unsupported"


class AcceptedArtifactKind(str, Enum):
    EXPECTED_OUTPUT = "expected_output"
    CHECKER_BUNDLE = "checker_bundle"


@dataclass
class VerifierProvenance:
    kind: str
    source_id: str
    schema_version: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OraclePlan:
    trainability_class: str
    primary_family_id: str
    fallback_family_id: Optional[str]
    route: OracleRoute
    acceptance_mode: str
    prompt_payloads: List[Dict[str, Any]] = field(default_factory=list)
    acceptance_threshold: float = 1.0
