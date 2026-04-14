"""
Inference layer: from a planner's problem description to solver augmentation.

Pipeline
--------
1.  Receive ``PlannerInput`` (problem, tags, rough direction).
2.  Retrieve the top-k most similar Q-nodes by tag overlap.
3.  For each retrieved Q-node, traverse its M-nodes.
4.  For each M-node, aggregate skill recommendations per FunctionBlock using
    the learned MS edge weights.
5.  Return a ``SolverAugmentation`` containing:
      - the original problem text
      - the merged sub-problem decomposition
      - ranked required skills with confidence scores
      - relevant error experiences as warnings

The inference engine is intentionally stateless (given the graph); it reads
edge weights but never modifies them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .blocks import ErrorExperience, SubProblem
from .graph import SolvitaSkillGraph
from .nodes import MNode, QNode, SNode
from .question_similarity import QuestionSimilarityWeights, sim_planner_to_qnode
from .types import NodeId, TagSet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# I/O data structures
# ---------------------------------------------------------------------------

@dataclass
class PlannerInput:
    """
    Payload passed from the Planner to the skill-graph inference engine.

    Fields
    ------
    problem_id:
        Optional identifier (may be absent for brand-new problems).
    description:
        Full problem statement text.
    tags:
        Algorithmic tags the planner has already inferred.
    direction:
        A rough natural-language hint about the intended approach
        (e.g. "divide-and-conquer on a segment tree").
    test_cases:
        Optional list of sample test case strings for context.
    similarity_description:
        Text for Sim semantic channel vs ``QNode.abstract_description``: normally planner
        ``canonical_problem`` serialized; if that is empty, **falls back to raw problem
        description** (set in ``build_planner_input``). ``None`` = legacy path using
        ``description + direction``.
    similarity_tags:
        Tags for Sim Jaccard vs ``q.tags`` / ``tags_level1``: normally planner
        ``algorithmic_tags``; if empty, **falls back to dataset tags** (same as
        ``PlannerInput.tags``, including ``algorithm_choice`` token split when missing).
        ``None`` = legacy: use ``tags`` field only.
    """
    description: str
    tags:        TagSet
    direction:   str
    problem_id:  Optional[str]        = None
    test_cases:  Optional[List[str]]  = None
    similarity_description: Optional[str] = None
    similarity_tags:        Optional[TagSet] = None


@dataclass
class SkillRecommendation:
    """
    A single skill recommendation, bundled with its aggregated confidence.

    ``contributing_blocks`` records which (m_node_id, block_id) pairs
    contributed to the score, for traceability.
    """
    skill:                SNode
    confidence:           float
    contributing_blocks:  List[Tuple[NodeId, str]] = field(default_factory=list)


@dataclass
class SolverAugmentation:
    """
    Enriched context returned to the Solver.

    Fields
    ------
    original_problem:
        Echoed back problem description.
    subproblems:
        Merged list of sub-problems from the top-k retrieved M-nodes.
    required_skills:
        Ranked list of (skill, confidence) recommendations.
    error_warnings:
        Error experiences from similar past problems that the Solver
        should be aware of.
    source_q_nodes:
        The Q-nodes that were retrieved as most similar (for debugging).
    """
    original_problem:  str
    subproblems:       List[SubProblem]
    required_skills:   List[SkillRecommendation]
    error_warnings:    List[ErrorExperience]
    source_q_nodes:    List[QNode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Inference engine
# ---------------------------------------------------------------------------

class GraphInference:
    """
    Read-only inference engine over a populated ``SolvitaSkillGraph``.

    Parameters
    ----------
    graph:
        A fully initialised (and ideally trained) skill graph.
    top_k_problems:
        How many Q-nodes to retrieve per query.
    top_k_skills:
        Maximum number of skill recommendations to return.
    skill_confidence_threshold:
        Minimum aggregated confidence for a skill to appear in output.
    max_error_warnings:
        Cap on the number of error experiences surfaced.
    """

    def __init__(
        self,
        graph:                       SolvitaSkillGraph,
        top_k_problems:              int   = 5,
        top_k_skills:                int   = 10,
        skill_confidence_threshold:  float = 0.05,
        max_error_warnings:          int   = 5,
        similarity_weights:          QuestionSimilarityWeights | None = None,
    ) -> None:
        self.graph                      = graph
        self.top_k_problems             = top_k_problems
        self.top_k_skills               = top_k_skills
        self.skill_confidence_threshold = skill_confidence_threshold
        self.max_error_warnings         = max_error_warnings
        self.similarity_weights         = similarity_weights or QuestionSimilarityWeights()

    # ------------------------------------------------------------------
    # Step 1 – retrieve similar Q-nodes
    # ------------------------------------------------------------------

    def retrieve_similar_problems(
        self, planner_input: PlannerInput
    ) -> List[Tuple[QNode, float]]:
        """
        Return the top-k Q-nodes most similar to ``planner_input``,
        along with their similarity scores, sorted descending.
        """
        scored: List[Tuple[QNode, float]] = []
        for q in self.graph.q_nodes.values():
            sim = sim_planner_to_qnode(
                planner_input, q, weights=self.similarity_weights
            )
            scored.append((q, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: self.top_k_problems]

    # ------------------------------------------------------------------
    # Step 2 – aggregate skill scores from retrieved M-nodes
    # ------------------------------------------------------------------

    def _aggregate_skills(
        self,
        m_nodes: List[MNode],
        q_sim_map: Dict[NodeId, float],
    ) -> Dict[str, Tuple[SNode, float, List[Tuple[NodeId, str]]]]:
        """
        For each M-node, iterate over every function block and accumulate
        weighted skill scores.

        ``q_sim_map`` maps **Q-node id** → Sim(q_new, q_i); each M-node uses
        ``m.source_problem_id`` to look up the matching similarity (path formula).

        Returns a dict keyed by SNode.node_id:
            {s_id: (SNode, accumulated_score, contributing_blocks)}
        """
        accum: Dict[str, Tuple[SNode, float, List[Tuple[NodeId, str]]]] = {}

        for m in m_nodes:
            q_sim = float(q_sim_map.get(m.source_problem_id, 0.0))
            for block in m.function_blocks:
                skill_pairs = self.graph.s_nodes_of_block(m.node_id, block.block_id)
                for snode, edge_w in skill_pairs:
                    contribution = edge_w * q_sim
                    if snode.node_id in accum:
                        prev_snode, prev_score, prev_blocks = accum[snode.node_id]
                        accum[snode.node_id] = (
                            prev_snode,
                            prev_score + contribution,
                            prev_blocks + [(m.node_id, block.block_id)],
                        )
                    else:
                        accum[snode.node_id] = (
                            snode,
                            contribution,
                            [(m.node_id, block.block_id)],
                        )
        return accum

    # ------------------------------------------------------------------
    # Step 3 – collect error experiences
    # ------------------------------------------------------------------

    def _collect_errors(self, m_nodes: List[MNode]) -> List[ErrorExperience]:
        errors: List[ErrorExperience] = []
        for m in m_nodes:
            errors.extend(m.error_experiences)
        return errors[: self.max_error_warnings]

    # ------------------------------------------------------------------
    # Step 4 – merge sub-problems (de-duplicate by description prefix)
    # ------------------------------------------------------------------

    def _merge_subproblems(self, m_nodes: List[MNode]) -> List[SubProblem]:
        seen:   Set[str]         = set()
        merged: List[SubProblem] = []
        for m in m_nodes:
            for sp in m.subproblems:
                key = sp.description[:60].lower()
                if key not in seen:
                    seen.add(key)
                    merged.append(sp)
        return merged

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def augment_for_solver(
        self, planner_input: PlannerInput
    ) -> SolverAugmentation:
        """
        Full inference pipeline: retrieve → aggregate → rank → return.
        """
        # Step 1: retrieve similar problems
        top_q_pairs = self.retrieve_similar_problems(planner_input)
        if not top_q_pairs:
            logger.warning(
                "No similar Q-nodes found for tags %s; "
                "returning empty augmentation.",
                planner_input.tags,
            )
            return SolverAugmentation(
                original_problem=planner_input.description,
                subproblems=[],
                required_skills=[],
                error_warnings=[],
            )

        source_q_nodes = [q for q, _ in top_q_pairs]

        # Step 2: collect M-nodes from retrieved Q-nodes
        # Important: each QNode may have 1 analysis MNode + multiple contrast MNodes.
        # We aggregate skills/subproblems only from analysis nodes to avoid duplicating
        # weights; contrast nodes are used only for error warnings.
        analysis_m_nodes: List[MNode] = []
        contrast_m_nodes: List[MNode] = []
        q_sim_map: Dict[NodeId, float] = {q.node_id: float(sim) for q, sim in top_q_pairs}
        for q, sim in top_q_pairs:
            m_list = self.graph.m_nodes_of(q.node_id)
            for m in m_list:
                if getattr(m, "kind", "analysis") == "contrast":
                    contrast_m_nodes.append(m)
                else:
                    analysis_m_nodes.append(m)

        # Step 3: aggregate skill scores  (ρ 与 Σ Sim·w_qm·w_ms 一致：每 M 使用其源 Q 的 Sim)
        skill_accum = self._aggregate_skills(analysis_m_nodes, q_sim_map)

        # Step 4: filter and rank
        recommendations: List[SkillRecommendation] = []
        for s_id, (snode, score, blocks) in skill_accum.items():
            if score >= self.skill_confidence_threshold:
                recommendations.append(
                    SkillRecommendation(
                        skill=snode,
                        confidence=score,
                        contributing_blocks=blocks,
                    )
                )
        recommendations.sort(key=lambda r: r.confidence, reverse=True)
        recommendations = recommendations[: self.top_k_skills]

        # Step 5: sub-problems and error warnings
        subproblems    = self._merge_subproblems(analysis_m_nodes)
        error_warnings = self._collect_errors(contrast_m_nodes)

        return SolverAugmentation(
            original_problem=planner_input.description,
            subproblems=subproblems,
            required_skills=recommendations,
            error_warnings=error_warnings,
            source_q_nodes=source_q_nodes,
        )

    def softmax_policy_rollout(
        self,
        planner_input: PlannerInput,
        sample_k: int,
        temperature: float = 1.0,
        rng=None,
    ):
        """
        Top-k Q by Sim(q_new, q_i), build ρ = Σ Sim·w_qm·w_ms, π = softmax(ρ/T),
        sample ``sample_k`` distinct skills without replacement; return
        :class:`~src.skill_graph.rl_rollout.SoftmaxRolloutResult` (paths + augmentation).

        Lazy-imports ``rl_rollout`` to avoid import cycles.
        """
        from .rl_rollout import softmax_rollout

        return softmax_rollout(
            self.graph,
            planner_input,
            top_k_problems=self.top_k_problems,
            sample_k=sample_k,
            temperature=temperature,
            similarity_weights=self.similarity_weights,
            rng=rng,
        )
