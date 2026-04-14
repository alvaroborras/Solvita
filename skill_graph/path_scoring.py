"""
Path-based skill scores ρ(s_k | q_new) aligned with the spec:

    ρ(s_k | q_new) = Σ Sim(q_new, q_i) · w_qm(i,j) · w_ms(j, k)

Summation is over retrieved Q-nodes q_i, their M-nodes m_j connected by QM edges,
and MS edges from function blocks in m_j to skill s_k.

Only **analysis** M-nodes (with function blocks / MS edges) contribute by default;
contrast nodes have empty blocks and are skipped.

We also track, for each skill s_k, the **single path** with maximum path score
(Sim·w_qm·w_ms) for interpretability and RL logging.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .graph import SolvitaSkillGraph
from .inference import PlannerInput
from .nodes import QNode
from .question_similarity import QuestionSimilarityWeights, sim_planner_to_qnode
from .types import EdgeId, NodeId


@dataclass(frozen=True)
class SkillPathContribution:
    """One concrete path q → m → (block) → s with multiplicative factors."""

    q_node_id:   NodeId
    m_node_id:   NodeId
    block_id:    str
    skill_id:    NodeId
    sim:         float
    w_qm:        float
    w_ms:        float
    path_score:  float
    qm_edge_id:  Optional[EdgeId]
    ms_edge_id:  Optional[EdgeId]


def compute_rho_and_best_paths(
    graph: SolvitaSkillGraph,
    planner: PlannerInput,
    candidate_q_nodes: List[QNode],
    *,
    similarity_weights: QuestionSimilarityWeights | None = None,
    analysis_only: bool = True,
) -> Tuple[Dict[NodeId, float], Dict[NodeId, SkillPathContribution]]:
    """
    Return ρ per skill and the best contributing path per skill (max path_score).
    """
    rho: Dict[NodeId, float] = defaultdict(float)
    best: Dict[NodeId, SkillPathContribution] = {}

    for q in candidate_q_nodes:
        sim = sim_planner_to_qnode(planner, q, weights=similarity_weights)
        if sim <= 0.0:
            continue
        for m in graph.m_nodes_of(q.node_id):
            if analysis_only and getattr(m, "kind", "analysis") == "contrast":
                continue
            qm = graph.get_qm_edge(q.node_id, m.node_id)
            w_qm = float(qm.weight) if qm is not None else 1.0
            qm_eid = qm.edge_id if qm is not None else None

            for block in m.function_blocks:
                bid = block.block_id
                for snode, w_ms in graph.s_nodes_of_block(m.node_id, bid):
                    w_ms_f = float(w_ms)
                    path_score = sim * w_qm * w_ms_f
                    sid = snode.node_id
                    rho[sid] += path_score

                    ms_e = graph.get_ms_edge(m.node_id, sid, bid)
                    ms_eid = ms_e.edge_id if ms_e is not None else None

                    prev = best.get(sid)
                    if prev is None or path_score > prev.path_score:
                        best[sid] = SkillPathContribution(
                            q_node_id=q.node_id,
                            m_node_id=m.node_id,
                            block_id=bid,
                            skill_id=sid,
                            sim=sim,
                            w_qm=w_qm,
                            w_ms=w_ms_f,
                            path_score=path_score,
                            qm_edge_id=qm_eid,
                            ms_edge_id=ms_eid,
                        )

    return dict(rho), best


def compute_rho_per_skill(
    graph: SolvitaSkillGraph,
    planner: PlannerInput,
    candidate_q_nodes: List[QNode],
    *,
    similarity_weights: QuestionSimilarityWeights | None = None,
    analysis_only: bool = True,
) -> Dict[NodeId, float]:
    """Return ρ(s_id) only (backward compat)."""
    rho, _ = compute_rho_and_best_paths(
        graph,
        planner,
        candidate_q_nodes,
        similarity_weights=similarity_weights,
        analysis_only=analysis_only,
    )
    return rho


def softmax_skill_distribution(
    rho: Dict[NodeId, float],
    temperature: float = 1.0,
) -> Dict[NodeId, float]:
    """Turn ρ values into a probability simplex π(s) = softmax(ρ / T)."""
    if not rho:
        return {}
    t = max(temperature, 1e-8)
    keys = list(rho.keys())
    vals = [rho[k] / t for k in keys]
    m = max(vals)
    exps = [math.exp(v - m) for v in vals]
    z = sum(exps)
    if z <= 0.0:
        u = 1.0 / len(keys)
        return {k: u for k in keys}
    return {k: e / z for k, e in zip(keys, exps)}


def log_prob_under_softmax(
    rho: Dict[NodeId, float],
    skill_id: NodeId,
    temperature: float = 1.0,
) -> float:
    """log π(s*) under softmax(ρ); uniform if skill not in support."""
    pi = softmax_skill_distribution(rho, temperature=temperature)
    p = pi.get(skill_id)
    if p is None or p <= 0.0:
        return -1e9
    return math.log(p)
