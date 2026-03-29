from __future__ import annotations

from typing import Any, Iterable

from src.oracle.catalog import build_oracle_catalog
from src.oracle.types import OraclePlan, OracleRoute

STABLE_FAMILY_IDS = (
    "oracle.enumeration.n_nested_loops",
    "oracle.dp.topdown",
)


def _pick_primary_family(problem_tags: Iterable[str], catalog: dict[str, dict[str, Any]]) -> str:
    tags = set(problem_tags or [])
    if "dp" in tags or "memoization" in tags:
        return "oracle.dp.topdown"
    return "oracle.enumeration.n_nested_loops"


def _build_candidate_family_ids(
    problem_tags: Iterable[str],
    catalog: dict[str, dict[str, Any]],
) -> list[str]:
    primary_family_id = _pick_primary_family(problem_tags, catalog)
    family_ids = [primary_family_id]
    for family_id in STABLE_FAMILY_IDS:
        if family_id != primary_family_id and family_id in catalog:
            family_ids.append(family_id)
    return family_ids


def build_rule_based_oracle_plan(
    *,
    trainability_class: str,
    problem_tags,
    problem_constraints,
    acceptance_mode: str,
) -> OraclePlan:
    del problem_constraints
    catalog = build_oracle_catalog()
    candidate_family_ids = _build_candidate_family_ids(problem_tags, catalog)
    family_id = candidate_family_ids[0]
    fallback_family_id = candidate_family_ids[1] if len(candidate_family_ids) > 1 else None
    route = (
        OracleRoute.EXACT_SINGLE_ANSWER
        if trainability_class == "exact_single_answer"
        else OracleRoute.TRUSTED_CHECKER_BACKED_MULTI
    )
    return OraclePlan(
        trainability_class=trainability_class,
        primary_family_id=family_id,
        fallback_family_id=fallback_family_id,
        route=route,
        acceptance_mode=acceptance_mode,
        prompt_payloads=[catalog[candidate_family_id] for candidate_family_id in candidate_family_ids],
        acceptance_threshold=0.95 if acceptance_mode == "safe" else 0.80,
    )
