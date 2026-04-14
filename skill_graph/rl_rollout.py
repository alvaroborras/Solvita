"""
Softmax policy over skills from path scores ρ, sampling, and rollout traces for RL.

ρ(s_k | q_new) = Σ Sim·w_qm·w_ms over paths q_i→m_j→s_k (see path_scoring).

π(s) = softmax(ρ / T).  Sampling k distinct skills uses sequential categorical draws
without replacement (probabilities renormalised after each pick), so we can report
a valid log-probability for the joint sample.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .graph import SolvitaSkillGraph
from .inference import PlannerInput, SkillRecommendation, SolverAugmentation
from .nodes import ErrorExperience, MNode, QNode, SNode
from .path_scoring import (
    SkillPathContribution,
    compute_rho_and_best_paths,
    softmax_skill_distribution,
)
from .question_similarity import QuestionSimilarityWeights, sim_planner_to_qnode
from .types import NodeId

logger = logging.getLogger(__name__)


@dataclass
class RolloutContext:
    """
    ρ / π 与激活子图上下文（在 softmax 采样或 LLM 选 skill 之前即可计算）。

    用于两阶段流程：先 ``compute_rollout_context``，再由策略或 LLM 产生 ``sampled_skill_ids``，
    最后 ``build_softmax_rollout_from_llm_skills`` 组装 ``SoftmaxRolloutResult``。
    """

    top_q_pairs:              List[Tuple[QNode, float]]
    rho:                      Dict[NodeId, float]
    best_path_per_skill:      Dict[NodeId, SkillPathContribution]
    pi:                       Dict[NodeId, float]
    temperature:              float
    analysis_m_nodes:         List[MNode]
    contrast_m_nodes:         List[MNode]
    similarity_weights:       QuestionSimilarityWeights


@dataclass
class SoftmaxRolloutResult:
    """Outcome of one softmax policy rollout (for solver injection + RL logging)."""

    rho:                      Dict[NodeId, float]
    pi:                       Dict[NodeId, float]
    temperature:              float
    top_q_pairs:              List[Tuple[QNode, float]]
    sampled_skill_ids:        List[NodeId]
    joint_log_prob_sample:    float
    best_path_per_skill:      Dict[NodeId, SkillPathContribution]
    sampled_paths:            List[SkillPathContribution]
    augmentation:             SolverAugmentation


def _sample_without_replacement(
    pi: Dict[NodeId, float],
    k: int,
    rng: random.Random,
) -> Tuple[List[NodeId], float]:
    """
    Sequential sampling without replacement; return (ids, log joint probability).
    """
    remaining = {sid: float(p) for sid, p in pi.items() if p > 0.0}
    if not remaining or k <= 0:
        return [], -math.inf

    picked: List[NodeId] = []
    log_joint = 0.0
    for _ in range(min(k, len(remaining))):
        z = sum(remaining.values())
        if z <= 0.0:
            break
        keys = list(remaining.keys())
        probs = [remaining[sid] / z for sid in keys]
        idx = rng.choices(range(len(keys)), weights=probs, k=1)[0]
        sid = keys[idx]
        p_take = probs[idx]
        log_joint += math.log(max(p_take, 1e-30))
        picked.append(sid)
        del remaining[sid]

    return picked, log_joint


def _sample_with_replacement(
    pi: Dict[NodeId, float],
    k: int,
    rng: random.Random,
) -> Tuple[List[NodeId], float]:
    """
    IID categorical sampling with replacement; return (ids, log joint probability).

    This matches the standard REINFORCE objective log p(a_1,...,a_k)=Σ log π(a_t).
    """
    support = [(sid, float(p)) for sid, p in pi.items() if p > 0.0]
    if not support or k <= 0:
        return [], -math.inf
    keys = [sid for sid, _ in support]
    weights = [p for _, p in support]
    picked: List[NodeId] = []
    log_joint = 0.0
    for _ in range(k):
        sid = rng.choices(keys, weights=weights, k=1)[0]
        p = float(pi.get(sid, 0.0))
        log_joint += math.log(max(p, 1e-30))
        picked.append(sid)
    return picked, log_joint


def build_solver_augmentation_from_sample(
    graph: SolvitaSkillGraph,
    planner: PlannerInput,
    sampled_skill_ids: Sequence[NodeId],
    best_path_per_skill: Dict[NodeId, SkillPathContribution],
    top_q_pairs: List[Tuple[QNode, float]],
    analysis_m_nodes: List[MNode],
    contrast_m_nodes: List[MNode],
    pi: Dict[NodeId, float],
) -> SolverAugmentation:
    """Build SolverAugmentation with one recommendation per sampled skill (path-aware)."""
    from .blocks import SubProblem

    seen: set[str] = set()
    merged_sub: List[SubProblem] = []
    for m in analysis_m_nodes:
        for sp in m.subproblems:
            key = sp.description[:60].lower()
            if key not in seen:
                seen.add(key)
                merged_sub.append(sp)

    errors: List[ErrorExperience] = []
    for m in contrast_m_nodes:
        errors.extend(m.error_experiences)

    # In strict mode we may sample with replacement, which can repeat skills.
    # Keep rollout.sampled_skill_ids as-is for logprob/gradient, but deduplicate
    # recommendations for a cleaner solver prompt.
    recs: List[SkillRecommendation] = []
    seen_skill: set[NodeId] = set()
    for sid in sampled_skill_ids:
        if sid in seen_skill:
            continue
        seen_skill.add(sid)
        snode = graph.s_nodes.get(sid)
        if snode is None:
            continue
        path = best_path_per_skill.get(sid)
        conf = float(pi.get(sid, 0.0))
        blocks: List[Tuple[NodeId, str]] = []
        if path is not None:
            blocks = [(path.m_node_id, path.block_id)]
        recs.append(
            SkillRecommendation(
                skill=snode,
                confidence=conf,
                contributing_blocks=blocks,
            )
        )

    return SolverAugmentation(
        original_problem=planner.description,
        subproblems=merged_sub,
        required_skills=recs,
        error_warnings=errors[:20],
        source_q_nodes=[q for q, _ in top_q_pairs],
    )


def compute_rollout_context(
    graph: SolvitaSkillGraph,
    planner: PlannerInput,
    *,
    top_k_problems: int,
    temperature: float = 1.0,
    similarity_weights: Optional[QuestionSimilarityWeights] = None,
) -> Optional[RolloutContext]:
    """
    计算 top-Q、ρ、π 及 analysis/contrast M 节点列表（不采样 skill）。

    供 **LLM 从 top-ρ 候选中自选 skill** 的流程在采样前复用同一套图分数。
    """
    w = similarity_weights or QuestionSimilarityWeights()
    scored: List[Tuple[QNode, float]] = []
    for q in graph.q_nodes.values():
        sim = sim_planner_to_qnode(planner, q, weights=w)
        scored.append((q, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    top_q_pairs = scored[: max(0, top_k_problems)]

    if not top_q_pairs:
        logger.warning("compute_rollout_context: no Q nodes in graph")
        return None

    candidate_q = [q for q, _ in top_q_pairs]
    rho, best_path = compute_rho_and_best_paths(
        graph,
        planner,
        candidate_q,
        similarity_weights=w,
        analysis_only=True,
    )
    pi = softmax_skill_distribution(rho, temperature=temperature)

    analysis_m: List[MNode] = []
    contrast_m: List[MNode] = []
    for q, _ in top_q_pairs:
        for m in graph.m_nodes_of(q.node_id):
            if getattr(m, "kind", "analysis") == "contrast":
                contrast_m.append(m)
            else:
                analysis_m.append(m)

    return RolloutContext(
        top_q_pairs=top_q_pairs,
        rho=rho,
        best_path_per_skill=best_path,
        pi=pi,
        temperature=temperature,
        analysis_m_nodes=analysis_m,
        contrast_m_nodes=contrast_m,
        similarity_weights=w,
    )


def build_softmax_rollout_from_llm_skills(
    graph: SolvitaSkillGraph,
    planner: PlannerInput,
    ctx: RolloutContext,
    llm_skill_ids: Sequence[NodeId],
) -> SoftmaxRolloutResult:
    """
    用大模型选定的 skill id 列表组装 ``SoftmaxRolloutResult``（用于提示与 strict RL 更新）。

    ``joint_log_prob_sample`` 取为 ``Σ_s log π(s)``（各选中 skill 独立，与旧版 IID 采样近似对齐）。
    """
    deduped: List[NodeId] = []
    seen: set[NodeId] = set()
    for sid in llm_skill_ids:
        sid = str(sid).strip()
        if not sid or sid not in graph.s_nodes or sid in seen:
            continue
        seen.add(sid)
        deduped.append(sid)

    pi = ctx.pi
    if not deduped:
        empty = SolverAugmentation(
            original_problem=planner.description,
            subproblems=[],
            required_skills=[],
            error_warnings=[],
        )
        return SoftmaxRolloutResult(
            rho=ctx.rho,
            pi=pi,
            temperature=ctx.temperature,
            top_q_pairs=ctx.top_q_pairs,
            sampled_skill_ids=[],
            joint_log_prob_sample=-math.inf,
            best_path_per_skill=ctx.best_path_per_skill,
            sampled_paths=[],
            augmentation=empty,
        )

    log_joint = sum(math.log(max(float(pi.get(s, 0.0)), 1e-30)) for s in deduped)
    aug = build_solver_augmentation_from_sample(
        graph,
        planner,
        deduped,
        ctx.best_path_per_skill,
        ctx.top_q_pairs,
        ctx.analysis_m_nodes,
        ctx.contrast_m_nodes,
        pi,
    )
    sampled_paths = [
        ctx.best_path_per_skill[s] for s in deduped if s in ctx.best_path_per_skill
    ]

    return SoftmaxRolloutResult(
        rho=ctx.rho,
        pi=pi,
        temperature=ctx.temperature,
        top_q_pairs=ctx.top_q_pairs,
        sampled_skill_ids=deduped,
        joint_log_prob_sample=log_joint,
        best_path_per_skill=ctx.best_path_per_skill,
        sampled_paths=sampled_paths,
        augmentation=aug,
    )


def softmax_rollout(
    graph: SolvitaSkillGraph,
    planner: PlannerInput,
    *,
    top_k_problems: int,
    sample_k: int,
    temperature: float = 1.0,
    similarity_weights: QuestionSimilarityWeights | None = None,
    rng: Optional[random.Random] = None,
    sample_with_replacement: bool = True,
) -> SoftmaxRolloutResult:
    """
    Top-k Q by Sim, then ρ over activated subgraph, softmax π, sample k skills.

    Uses analysis M-nodes only for ρ; contrast M-nodes only for error warnings.
    """
    rng = rng or random.Random()

    ctx = compute_rollout_context(
        graph,
        planner,
        top_k_problems=top_k_problems,
        temperature=temperature,
        similarity_weights=similarity_weights,
    )
    if ctx is None:
        empty = SolverAugmentation(
            original_problem=planner.description,
            subproblems=[],
            required_skills=[],
            error_warnings=[],
        )
        return SoftmaxRolloutResult(
            rho={},
            pi={},
            temperature=temperature,
            top_q_pairs=[],
            sampled_skill_ids=[],
            joint_log_prob_sample=-math.inf,
            best_path_per_skill={},
            sampled_paths=[],
            augmentation=empty,
        )

    pi = ctx.pi
    if sample_with_replacement:
        sampled_ids, joint_log = _sample_with_replacement(pi, sample_k, rng)
    else:
        sampled_ids, joint_log = _sample_without_replacement(pi, sample_k, rng)

    sampled_paths = [
        ctx.best_path_per_skill[sid] for sid in sampled_ids if sid in ctx.best_path_per_skill
    ]

    aug = build_solver_augmentation_from_sample(
        graph,
        planner,
        sampled_ids,
        ctx.best_path_per_skill,
        ctx.top_q_pairs,
        ctx.analysis_m_nodes,
        ctx.contrast_m_nodes,
        pi,
    )

    return SoftmaxRolloutResult(
        rho=ctx.rho,
        pi=pi,
        temperature=temperature,
        top_q_pairs=ctx.top_q_pairs,
        sampled_skill_ids=sampled_ids,
        joint_log_prob_sample=joint_log,
        best_path_per_skill=ctx.best_path_per_skill,
        sampled_paths=sampled_paths,
        augmentation=aug,
    )
