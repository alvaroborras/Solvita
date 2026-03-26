from __future__ import annotations

from typing import Any, Iterable

from src.oracle.catalog import build_oracle_catalog
from src.oracle.types import OraclePlan, OracleRoute


def _pick_primary_family(problem_tags: Iterable[str], catalog: dict[str, dict[str, Any]]) -> str:
    tags = set(problem_tags or [])
    if "dp" in tags or "memoization" in tags:
        return "oracle.dp.topdown"
    if "graph" in tags or "dfs" in tags:
        return "oracle.graph.all_paths"
    return next(iter(catalog))


def build_rule_based_oracle_plan(
    *,
    trainability_class: str,
    problem_tags,
    problem_constraints,
    acceptance_mode: str,
) -> OraclePlan:
    del problem_constraints
    catalog = build_oracle_catalog()
    family_id = _pick_primary_family(problem_tags, catalog)
    route = (
        OracleRoute.EXACT_SINGLE_ANSWER
        if trainability_class == "exact_single_answer"
        else OracleRoute.TRUSTED_CHECKER_BACKED_MULTI
    )
    return OraclePlan(
        trainability_class=trainability_class,
        primary_family_id=family_id,
        fallback_family_id=None,
        route=route,
        acceptance_mode=acceptance_mode,
        prompt_payloads=[catalog[family_id]],
        acceptance_threshold=0.95 if acceptance_mode == "safe" else 0.80,
    )
