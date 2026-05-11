"""
Solver skill planning — runs after TestGen, before CodeGen, when ``solver_network.enabled``.

Mirrors ``skill_graph_train.pipeline.run_episode``: ``compute_rollout_context`` → LLM skill + DAG
→ ``build_softmax_rollout_from_llm_skills`` (or ``softmax_rollout`` fallback) → markdown block for codegen
and ``plan.implementation_steps`` / ``plan.algorithm_choice`` from the DAG.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

import src.events as events
from skill_graph import GraphStore
from skill_graph.rl_rollout import (
    build_softmax_rollout_from_llm_skills,
    compute_rollout_context,
    softmax_rollout,
)

from src.solver_network.adapter import build_augmentation_block_from_rollout
from src.solver_network.graph_prompts import format_selected_skills_content_by_ids
from src.solver_network.llm_skill_selection import (
    SkillSelectionResult,
    format_skill_ids_for_log,
    llm_select_skills,
    normalize_subproblem_dag,
    subproblem_dag_nonempty,
)
from src.solver_network.planner_input import build_planner_input_from_state

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _problem_summary_for_selection(state: Dict[str, Any]) -> str:
    canonical = (state.get("problem") or {}).get("canonical", {}) or {}
    raw_desc = (state.get("problem") or {}).get("description", "") or ""
    objective = canonical.get("objective", "")
    if objective:
        return f"{objective}\n\n{raw_desc}".strip()
    return str(raw_desc).strip()


def _implementation_steps_from_subproblem_dag(dag: Dict[str, Any]) -> List[str]:
    """Topological order of DAG nodes → implementation step lines (training pipeline)."""
    if not isinstance(dag, dict):
        return []
    nodes = dag.get("nodes") or []
    edges = dag.get("edges") or []
    id_to_desc: Dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        i = str(n.get("id", "") or "").strip()
        if not i:
            continue
        id_to_desc[i] = str(n.get("description", "") or "").strip()
    if not id_to_desc:
        return []
    if not edges:
        out: List[str] = []
        for n in nodes:
            if isinstance(n, dict):
                nid = str(n.get("id", "") or "").strip()
                d = str(n.get("description", "") or "").strip()
                if nid or d:
                    out.append(f"{nid}: {d}" if nid else d)
        return out

    adj: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = defaultdict(int)
    for k in id_to_desc:
        indeg[k] = 0
    for e in edges:
        if not isinstance(e, dict):
            continue
        a = str(e.get("from_id", e.get("from", "")) or "").strip()
        b = str(e.get("to_id", e.get("to", "")) or "").strip()
        if a in id_to_desc and b in id_to_desc:
            adj[a].append(b)
            indeg[b] += 1
    queue = deque([k for k in id_to_desc if indeg[k] == 0])
    order: List[str] = []
    while queue:
        u = queue.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    if len(order) < len(id_to_desc):
        order = list(id_to_desc.keys())
    return [f"{i}: {id_to_desc[i]}" for i in order if id_to_desc.get(i)]


def _merge_skill_selection_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(cfg)
    sn = cfg.get("solver_network") or {}
    if sn.get("skill_selection_temperature") is not None:
        out["skill_selection_temperature"] = sn["skill_selection_temperature"]
    if sn.get("skill_selection_temperature_first") is not None:
        out["skill_selection_temperature_first"] = sn["skill_selection_temperature_first"]
    if sn.get("skill_selection_planner_max_chars") is not None:
        out["skill_selection_planner_max_chars"] = sn["skill_selection_planner_max_chars"]
    return out


def _run_skill_plan(state: "SolvitaState") -> Dict[str, Any]:
    """
    Core skill-plan logic. Returns keys: plan, execution_log, llm_calls (same shape as node output).
    """
    cfg = state["config"]
    sn = cfg.get("solver_network") or {}
    if not sn.get("enabled"):
        return {
            "plan": {
                "algorithm_choice": "",
                "implementation_steps": [],
                "solver_graph_augmentation_block": "",
                "skill_selection_skill_ids": [],
                "skill_selection_subproblem_dag": {},
                "skill_selection_skills_content_md": "",
            },
            "execution_log": ["Solver skill plan: skipped (solver_network disabled)"],
            "llm_calls": 0,
        }

    graph_dir = (sn.get("graph_dir") or "").strip()
    if not graph_dir:
        logger.warning("[solver_skill_plan] enabled but graph_dir empty")
        return {
            "plan": {
                "algorithm_choice": "",
                "implementation_steps": [],
                "solver_graph_augmentation_block": "",
            },
            "execution_log": ["Solver skill plan: skipped (no graph_dir)"],
            "llm_calls": 0,
        }

    try:
        store = GraphStore(graph_dir)
        graph = store.load()
    except Exception as exc:
        logger.warning("[solver_skill_plan] failed to load graph: %s", exc)
        return {
            "plan": {
                "algorithm_choice": "",
                "implementation_steps": [],
                "solver_graph_augmentation_block": "",
            },
            "execution_log": [f"Solver skill plan: load failed ({exc})"],
            "llm_calls": 0,
        }

    planner = build_planner_input_from_state(state)
    top_k = int(sn.get("top_k_problems", 4))
    sample_k = int(sn.get("sample_k", 5))
    temperature = float(sn.get("temperature", 1.0))

    llm_calls = 0
    try:
        ctx = compute_rollout_context(
            graph,
            planner,
            top_k_problems=top_k,
            temperature=temperature,
        )
    except Exception as exc:
        logger.warning("[solver_skill_plan] compute_rollout_context failed: %s", exc)
        ctx = None

    merge_cfg = _merge_skill_selection_config(cfg)
    summary = _problem_summary_for_selection(state)
    candidate_k = int(sn.get("skill_candidate_k", 20))
    min_sk = int(sn.get("min_llm_skills", 1))
    max_sk = int(sn.get("max_llm_skills", 5))

    sel: SkillSelectionResult
    rollout: Any
    llm_returned_no_skills = False

    if ctx is None:
        logger.warning("[solver_skill_plan] no rollout context; using softmax_rollout only")
        rollout = softmax_rollout(
            graph,
            planner,
            top_k_problems=top_k,
            sample_k=sample_k,
            temperature=temperature,
        )
        sel = SkillSelectionResult(list(rollout.sampled_skill_ids or []), {})
    else:
        sel = llm_select_skills(
            merge_cfg,
            summary,
            graph,
            ctx.rho,
            candidate_k=candidate_k,
            min_select=min_sk,
            max_select=max_sk,
            state=state,
            rollout_ctx=ctx,
        )
        llm_calls += 1

        if sel.skill_ids:
            rollout = build_softmax_rollout_from_llm_skills(graph, planner, ctx, sel.skill_ids)
        else:
            preserved = normalize_subproblem_dag(sel.subproblem_dag)
            rollout = softmax_rollout(
                graph,
                planner,
                top_k_problems=top_k,
                sample_k=sample_k,
                temperature=temperature,
            )
            if subproblem_dag_nonempty(preserved):
                logger.info(
                    "[solver_skill_plan] LLM returned no skills; keeping DAG for codegen steps"
                )
                sel = SkillSelectionResult([], preserved)
            llm_returned_no_skills = True

    dag_norm = normalize_subproblem_dag(sel.subproblem_dag)
    steps = _implementation_steps_from_subproblem_dag(dag_norm)
    if steps:
        algo = steps[0]
        if len(algo) > 220:
            algo = algo[:217] + "..."
    else:
        algo = ""

    skill_md = ""
    if sel.skill_ids:
        skill_md = format_selected_skills_content_by_ids(graph, sel.skill_ids)

    if llm_returned_no_skills:
        skill_block = ""
    else:
        skill_block = build_augmentation_block_from_rollout(graph, rollout, sn)

    plan_patch: Dict[str, Any] = {
        "skill_selection_subproblem_dag": dag_norm,
        "skill_selection_skill_ids": list(sel.skill_ids),
        "skill_selection_skills_content_md": skill_md,
        "implementation_steps": steps,
        "algorithm_choice": algo or "Follow the subproblem plan and graph-backed skills below.",
        "solver_graph_augmentation_block": skill_block,
    }

    skill_detail = format_skill_ids_for_log(graph, sel.skill_ids) if sel.skill_ids else "(none)"
    if sel.skill_ids:
        if llm_calls:
            logger.info("[solver_skill_plan] LLM-selected skills: {}", skill_detail)
        else:
            logger.info("[solver_skill_plan] Rollout-sampled skills (no activated context): {}", skill_detail)

    return {
        "plan": plan_patch,
        "execution_log": [
            f"Solver skill plan: selected_skills={skill_detail} "
            f"dag_nodes={len(dag_norm.get('nodes') or [])} block_chars={len(skill_block)} "
            f"llm_skill_calls={llm_calls}",
        ],
        "llm_calls": llm_calls,
    }


def run_skill_plan_once(state: "SolvitaState") -> Dict[str, Any]:
    """Alias for ensemble / tests: same return shape as ``solver_skill_plan_node``."""
    return _run_skill_plan(state)


def solver_skill_plan_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Populate ``plan`` with skill-graph rollout, optional LLM skill + DAG selection, and the
    preformatted ``solver_graph_augmentation_block`` for ``generate_code_node``.
    """
    events.emit("phase_start", phase="solver_skill_plan", label="Planning Strategy")
    result = _run_skill_plan(state)
    algo = (result.get("plan") or {}).get("algorithm_choice", "")
    events.emit("phase_done", phase="solver_skill_plan", label="Planning Strategy",
                data={"algorithm": algo})
    return result
