"""
Step 8 — graph self-evolution after each training episode.

模板与离线管线一致：``skill_graph_train/prompt_template/correct_solution_logic_chain.txt``、
``correct_vs_incorrect_logic_diff.txt``；调用封装见 ``evolution_llm``（路径由 ``prompt_template_dir`` 解析）。

新 Q 的 **一二级 tags** 与 **抽象数学描述** 复用 planner（``state.plan`` / ``state.problem.canonical``），不调新 LLM。

自进化规则里 **A = with** 提交、**B = without** 提交（见 ``skill_graph.self_evolution``）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from skill_graph import Outcome
from skill_graph.self_evolution import (
    EvolutionInput,
    SolveCandidate,
    build_self_evolution_plan,
    official_correct_from_record,
)

from skill_graph_train.evolution_apply import apply_evolution_plan_to_graph

logger = logging.getLogger(__name__)


def _ac_passed(pass_rate: float, outcome: Any) -> bool:
    if outcome == Outcome.COMPILATION_ERROR:
        return False
    try:
        return float(pass_rate) >= 1.0 - 1e-9
    except (TypeError, ValueError):
        return False


def _tags_and_abstract_from_state(
    state: Dict[str, Any],
    planner_description: str,
    record: Dict[str, Any],
) -> tuple[List[str], List[str], str, str]:
    """(tags_level1, tags_level2, abstract_description, raw_description)."""
    from skill_graph_train.pipeline import canonical_text_for_similarity  # defer: breaks cycle with pipeline

    problem = state.get("problem") or {}
    plan = state.get("plan") or {}
    raw_desc = str(problem.get("description") or record.get("description") or "").strip()

    algo_tags = plan.get("algorithmic_tags") or []
    if isinstance(algo_tags, str):
        algo_tags = [algo_tags]
    tags_l1 = [str(t).strip().lower() for t in algo_tags if str(t).strip()]

    if not tags_l1:
        pt = record.get("tags")
        if isinstance(pt, str):
            tags_l1 = [pt.strip().lower()] if pt.strip() else []
        elif isinstance(pt, list):
            tags_l1 = [str(t).strip().lower() for t in pt if str(t).strip()]

    tl2 = record.get("tags_level2")
    if isinstance(tl2, str) and tl2.strip():
        tags_l2 = [tl2.strip().lower()]
    elif isinstance(tl2, list):
        tags_l2 = [str(x).strip().lower() for x in tl2 if str(x).strip()]
    else:
        tags_l2 = []

    canon = problem.get("canonical") or {}
    abstract = (canonical_text_for_similarity(canon) if isinstance(canon, dict) else "").strip()
    if not abstract:
        abstract = raw_desc or planner_description

    return tags_l1, tags_l2, abstract[:16000], raw_desc


def on_episode_finished(context: Dict[str, Any]) -> None:
    if not context.get("skill_graph_evolution"):
        return
    if not context.get("contrastive_llm", True):
        logger.debug("evolution_hook: contrastive_llm off; skip")
        return
    graph = context.get("graph")
    record = context.get("record")
    cfg = context.get("config") or {}
    planner = context.get("planner")
    state = context.get("state") or {}
    if graph is None or record is None or planner is None:
        logger.debug("evolution_hook: missing graph/record/planner; skip")
        return

    pwo = float(context.get("pass_without") or 0.0)
    owo = context.get("outcome_without")
    code_wo = str(context.get("code_without") or "")
    pw = float(context.get("pass_with") or 0.0)
    ow = context.get("outcome_with")
    code_with = str(context.get("code_with") or "")

    no_skill = SolveCandidate(
        candidate_id="no_skill",
        code=code_wo,
        passed=_ac_passed(pwo, owo),
        pass_rate=pwo,
        score=float(pwo),
        from_skill_path=False,
        skill_id="",
    )
    with_skill = SolveCandidate(
        candidate_id="with_skill",
        code=code_with,
        passed=_ac_passed(pw, ow),
        pass_rate=pw,
        score=float(pw),
        from_skill_path=True,
        skill_id="",
    )

    official = official_correct_from_record(record)

    plan = build_self_evolution_plan(
        EvolutionInput(
            no_skill_candidate=no_skill,
            with_skill_candidate=with_skill,
            official_correct_solution=official,
        )
    )

    if not plan.create_qi:
        logger.info("evolution_hook: no new Q/M (notes=%s)", plan.notes)
        return

    desc = getattr(planner, "description", "") or str(record.get("description", ""))
    tags_l1, tags_l2, abstract, raw_desc = _tags_and_abstract_from_state(state, desc, record)

    ok, notes = apply_evolution_plan_to_graph(
        graph,
        plan,
        config=cfg,
        record=record,
        problem_description=desc,
        tags_level1=tags_l1,
        tags_level2=tags_l2,
        abstract_description=abstract,
        raw_description=raw_desc,
    )
    if ok:
        logger.info("evolution_hook: attached evolved nodes (%s)", notes[-1] if notes else ok)
    else:
        logger.warning("evolution_hook: evolution failed notes=%s", notes)
