"""Build optional one-shot skill-graph text block for initial codegen."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from loguru import logger

from skill_graph import GraphStore, softmax_rollout
from skill_graph.graph import SolvitaSkillGraph
from skill_graph.rl_rollout import SoftmaxRolloutResult

from .graph_prompts import (
    format_enriched_path_context,
    format_selected_skills_content_by_ids,
    format_skill_augmentation,
)
from .planner_input import build_planner_input_from_state


def build_augmentation_block_from_rollout(
    graph: SolvitaSkillGraph,
    rollout: SoftmaxRolloutResult,
    sn: Dict[str, Any],
) -> str:
    """
    Format rollout into the markdown block appended to codegen (matches training ``run_episode`` assembly).
    """
    include_tmpl = bool(sn.get("include_skill_templates_in_augmentation", False))
    aug = rollout.augmentation
    skill_ids = rollout.sampled_skill_ids
    parts: list[str] = ["## Skill graph rollout (one-shot)\n"]
    parts.append(
        format_skill_augmentation(aug, include_required_skill_templates=include_tmpl)
    )
    if skill_ids and not include_tmpl:
        skill_md = format_selected_skills_content_by_ids(graph, skill_ids)
        if skill_md.strip():
            parts.append("### Selected skill references (templates from graph)\n")
            parts.append(skill_md)
    if skill_ids:
        path_idx = 5 if include_tmpl else 4
        path_block = format_enriched_path_context(
            graph,
            rollout.best_path_per_skill,
            rollout.pi,
            skill_ids,
            section_index=path_idx,
        )
        if path_block.strip():
            parts.append(path_block)

    return "\n\n".join(p for p in parts if p and p.strip()).strip()


def build_solver_network_block(state: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Return formatted skill-graph context for the first codegen call only.

    If ``plan.solver_graph_augmentation_block`` is already set (by ``solver_skill_plan_node``), returns it.
    Otherwise runs an on-the-fly ``softmax_rollout`` (legacy / scripts that skip the planning node).

    When disabled, graph dir missing, or load fails, returns an empty string and logs.
    """
    sn = config.get("solver_network") or {}
    pre = (state.get("plan") or {}).get("solver_graph_augmentation_block")
    if isinstance(pre, str) and pre.strip():
        return pre.strip()

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

    planner = build_planner_input_from_state(state)
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

    return build_augmentation_block_from_rollout(graph, rollout, sn)
