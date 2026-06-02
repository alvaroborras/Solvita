from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

import src.events as events
from src.failure_bank import FailureBankService

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _empty_failure_bank_context() -> Dict[str, Any]:
    return {
        "matched_patterns": [],
        "retrieved_counterexamples": [],
        "anti_patterns": [],
        "repair_summaries": [],
        "source_case_ids": [],
    }


def failure_bank_lookup_node(state: "SolvitaState") -> Dict[str, Any]:
    events.emit_node_enter("failure_bank_lookup", "top")
    config = ((state.get("config") or {}).get("failure_bank") or {})
    if not bool(config.get("enabled", True)):
        return {
            "failure_bank_context": _empty_failure_bank_context(),
            "execution_log": ["Failure bank lookup: disabled"],
        }

    data_dir = str(config.get("data_dir", "") or "")
    if not data_dir:
        return {
            "failure_bank_context": _empty_failure_bank_context(),
            "execution_log": ["Failure bank lookup: skipped (no data_dir configured)"],
        }

    service = FailureBankService(data_dir)
    service.initialize()

    problem = state.get("problem") or {}
    canonical = problem.get("canonical") or {}
    canonical_objective = str(canonical.get("objective", "") or problem.get("description", "") or "")
    tags_level1 = list(problem.get("tags_selected", []) or [])
    tags_level2 = list(problem.get("tags_level2_selected", []) or [])
    lookup_limit = int(config.get("lookup_limit", 3) or 3)

    context = service.lookup_context(
        canonical_objective=canonical_objective,
        tags_level1=tags_level1,
        tags_level2=tags_level2,
        lookup_limit=lookup_limit,
    )
    return {
        "failure_bank_context": context,
        "execution_log": [
            "Failure bank lookup: "
            f"patterns={len(context['matched_patterns'])} "
            f"counterexamples={len(context['retrieved_counterexamples'])}"
        ],
    }
