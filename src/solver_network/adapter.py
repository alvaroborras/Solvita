"""Build optional one-shot skill-graph text block for initial codegen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from skill_graph import GraphStore, PlannerInput, softmax_rollout

from .graph_prompts import format_enriched_path_context, format_skill_augmentation


def _planner_from_state(state: Dict[str, Any]) -> PlannerInput:
    raw_desc = state.get("problem", {}).get("description", "") or ""
    tags = state.get("problem", {}).get("tags_selected") or []
    canon = state.get("problem", {}).get("canonical") or {}
    direction = state.get("plan", {}).get("algorithm_choice", "") or ""
    similarity_desc = json.dumps(canon, indent=2, ensure_ascii=False) if canon else None
    return PlannerInput(
        description=raw_desc,
        tags=list(tags),
        direction=str(direction),
        similarity_description=similarity_desc or raw_desc,
        similarity_tags=list(tags),
    )


def build_solver_network_block(state: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Return formatted skill-graph context for the first codegen call only.

    When disabled, graph dir missing, or load fails, returns an empty string and logs.
    """
    sn = config.get("solver_network") or {}
    if not sn.get("enabled"):
        return ""

    graph_dir = (sn.get("graph_dir") or "").strip()
    if not graph_dir:
        logger.warning("[SolverNetwork] enabled but solver_network.graph_dir is empty; skipping injection")
        return ""

    gpath = Path(graph_dir)
    if not gpath.is_dir():
        logger.warning("[SolverNetwork] graph_dir is not a directory: %s; skipping injection", graph_dir)
        return ""

    try:
        store = GraphStore(str(gpath))
        graph = store.load()
    except FileNotFoundError as exc:
        logger.warning("[SolverNetwork] failed to load graph: %s", exc)
        return ""
    except Exception as exc:
        logger.warning("[SolverNetwork] unexpected error loading graph: %s", exc)
        return ""

    planner = _planner_from_state(state)
    top_k = int(sn.get("top_k_problems", 4))
    sample_k = int(sn.get("sample_k", 5))
    temperature = float(sn.get("temperature", 1.0))

    try:
        rollout = softmax_rollout(
            graph,
            planner,
            top_k_problems=top_k,
            sample_k=sample_k,
            temperature=temperature,
        )
    except Exception as exc:
        logger.warning("[SolverNetwork] softmax_rollout failed: %s", exc)
        return ""

    aug = rollout.augmentation
    skill_ids = rollout.sampled_skill_ids
    parts: list[str] = ["## Skill graph rollout (one-shot)\n"]
    parts.append(format_skill_augmentation(aug, include_required_skill_templates=True))
    if skill_ids:
        path_block = format_enriched_path_context(
            graph,
            rollout.best_path_per_skill,
            rollout.pi,
            skill_ids,
            section_index=5,
        )
        if path_block.strip():
            parts.append(path_block)

    text = "\n\n".join(p for p in parts if p and p.strip())
    return text.strip()
