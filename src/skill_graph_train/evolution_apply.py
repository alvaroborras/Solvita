"""Attach evolved Q/M nodes to :class:`SolvitaSkillGraph` (QM + MS initialisation)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from skill_graph import (
    Dataset,
    EdgeWeightInitializer,
    MNode,
    QMEdge,
    QNode,
    SimilarityMetric,
    SolvitaSkillGraph,
)
from skill_graph.qm_init_weights import qm_weights_per_m_kind
from skill_graph.tag_utils import canonicalize_tag_set
from skill_graph.mnode_from_logic_dict import analysis_mnode_from_logic_analysis, contrast_mnode_from_logic_contrast
from skill_graph.self_evolution import EvolutionPlan

from skill_graph_train.evolution_llm import run_logic_chain, run_logic_diff

logger = logging.getLogger(__name__)


def _wire_qm_edges(graph: SolvitaSkillGraph, q_id: str, analysis: Optional[MNode], contrasts: List[MNode]) -> None:
    analysis_nodes = [analysis] if analysis is not None else []
    contrast_nodes = list(contrasts)

    w_analysis_each, w_contrast_each = qm_weights_per_m_kind(
        len(analysis_nodes), len(contrast_nodes)
    )

    for m in analysis_nodes:
        graph.add_edge(
            QMEdge(
                source_id=q_id,
                target_id=m.node_id,
                weight=w_analysis_each,
                trainable=True,
            )
        )
    for m in contrast_nodes:
        graph.add_edge(
            QMEdge(
                source_id=q_id,
                target_id=m.node_id,
                weight=w_contrast_each,
                trainable=True,
            )
        )


def apply_evolution_plan_to_graph(
    graph: SolvitaSkillGraph,
    plan: EvolutionPlan,
    *,
    config: Dict[str, Any],
    record: Dict[str, Any],
    problem_description: str,
    tags_level1: List[str],
    tags_level2: Optional[List[str]] = None,
    abstract_description: str,
    raw_description: str,
) -> Tuple[bool, List[str]]:
    """
    Run logic_chain (always) and optional logic_diff; register Q + M.

    ``plan.correct_solutions_for_q`` / ``incorrect_solutions_for_q`` 写入新 Q（与其它 Q 节点字段对齐）。
    """
    notes: List[str] = list(plan.notes)
    if not plan.create_qi:
        return False, notes

    pid = str(record.get("problem_id") or record.get("id") or "").strip()
    if pid and any(getattr(q, "problem_id", "") == pid for q in graph.q_nodes.values()):
        notes.append(f"skip_evolution: problem_id={pid!r} already in graph")
        return False, notes

    ds_raw = record.get("dataset")
    try:
        dataset = Dataset.from_str(str(ds_raw)) if ds_raw else Dataset.UNKNOWN
    except Exception:
        dataset = Dataset.UNKNOWN

    l1 = sorted(canonicalize_tag_set(tags_level1))
    l2 = sorted(canonicalize_tag_set(tags_level2 or []))
    tags_union = sorted(set(l1) | set(l2)) if l2 else list(l1)

    q = QNode(
        problem_id=pid or "_evolved_pending_",
        abstract_description=(abstract_description or raw_description or problem_description)[:16000],
        tags=tags_union,
        tags_level1=l1,
        tags_level2=l2,
        correct_solutions=list(plan.correct_solutions_for_q),
        incorrect_solutions=list(plan.incorrect_solutions_for_q),
        test_cases=[],
        dataset=dataset,
        metadata={
            "evolved": True,
            "description": (raw_description or "")[:12000] or (abstract_description or "")[:2000],
            "evolution_notes": "; ".join(plan.notes),
        },
    )
    if not pid:
        q.problem_id = f"evolved_{q.node_id}"

    cc = (plan.logic_chain_code or "").strip()
    if not cc:
        notes.append("empty_logic_chain_code")
        return False, notes

    edge_init = EdgeWeightInitializer(
        metric=SimilarityMetric.EMBEDDING,
        top_k_per_block=16,
    )

    tags_csv = ", ".join(tags_union) if tags_union else ", ".join(l1)

    la = run_logic_chain(
        config,
        description=problem_description,
        tags_csv=tags_csv,
        correct_code=cc,
    )
    if not la:
        notes.append("logic_chain_failed")
        return False, notes

    analysis_m = analysis_mnode_from_logic_analysis(
        q.node_id,
        la,
        problem_tags=tags_union,
        metadata={"evolution": True, "logic_chain_source": "episode"},
    )

    contrast_ms: List[MNode] = []
    for i, wrong in enumerate(plan.contrast_wrong_codes):
        w = (wrong or "").strip()
        if not w:
            continue
        diff = run_logic_diff(
            config,
            description=problem_description,
            tags_csv=tags_csv,
            correct_code=cc,
            incorrect_code=w,
            logic_analysis=la,
        )
        if not diff:
            notes.append(f"logic_diff_failed_{i}")
            continue
        cm = contrast_mnode_from_logic_contrast(
            q.node_id,
            analysis_m.function_blocks,
            incorrect_index=i,
            logic_contrast=diff,
            metadata={"evolution": True, "wrong_index": i},
        )
        contrast_ms.append(cm)

    graph.add_node(q)
    graph.add_node(analysis_m)
    edge_init.initialize_m_node(graph, analysis_m)
    for cm in contrast_ms:
        graph.add_node(cm)
        edge_init._copy_ms_from_analysis(graph, analysis_m, cm)  # noqa: SLF001

    _wire_qm_edges(graph, q.node_id, analysis_m, contrast_ms)
    notes.append(
        f"evolution_attached q={q.node_id} analysis={analysis_m.node_id} n_contrast={len(contrast_ms)}"
    )
    logger.info("Graph evolution: %s", notes[-1])
    return True, notes
