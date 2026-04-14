"""
Build :class:`MNode` instances from ``logic_analysis`` / ``logic_contrast`` dicts.

Mirrors the construction logic in :mod:`skill_graph.data_loader` for offline JSONL;
used by runtime graph self-evolution after LLM extraction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .blocks import BlockDifference, BlockToSubproblem, DAGLink, ErrorExperience, FunctionBlock, SubProblem
from .nodes import MNode
from .tag_utils import canonicalize_tag_set, canonicalize_text, canonicalize_tag


def _infer_function_block_tags(role: str, problem_tags: Sequence[str]) -> List[str]:
    if not role:
        return []
    cr = canonicalize_text(role)
    out: List[str] = []
    for t in problem_tags:
        ct = canonicalize_tag(t)
        if not ct:
            continue
        token_underscore = ct
        token_space = ct.replace("_", " ")
        if token_underscore in cr.replace("_", " ") or token_space in cr:
            out.append(ct)
    seen: set[str] = set()
    dedup: List[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


def analysis_mnode_from_logic_analysis(
    qnode_id: str,
    la: Dict[str, Any],
    *,
    problem_tags: Sequence[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> MNode:
    """Single **analysis** M-node from a ``logic_analysis``-shaped dict."""
    tags = list(canonicalize_tag_set(problem_tags))
    requirements = la.get("requirements", []) or []
    fn_blocks = la.get("function_blocks", []) or []
    sub_dag = la.get("sub_problem_dag") or {}
    block_to_sub = la.get("block_to_subproblem", []) or []

    function_blocks: List[FunctionBlock] = []
    for b in fn_blocks:
        block_id = str(b.get("id"))
        name_or_label = str(b.get("name_or_label", ""))
        role = str(b.get("role", ""))
        inferred_tags = _infer_function_block_tags(role, tags)
        function_blocks.append(
            FunctionBlock(
                id=block_id,
                name_or_label=name_or_label,
                role=role,
                tags=inferred_tags,
                code="",
                metadata={},
            )
        )

    subproblems: List[SubProblem] = []
    for sn in (sub_dag.get("nodes", []) or []):
        subproblems.append(
            SubProblem(
                id=str(sn.get("id")),
                description=str(sn.get("description", "")),
                metadata={},
            )
        )

    dag_links: List[DAGLink] = []
    for ed in (sub_dag.get("edges", []) or []):
        dag_links.append(
            DAGLink.new(
                from_id=str(ed.get("from_id")),
                to_id=str(ed.get("to_id")),
            )
        )

    block_to_subproblem: List[BlockToSubproblem] = []
    for m in block_to_sub:
        block_to_subproblem.append(
            BlockToSubproblem(
                block_id=str(m.get("block_id")),
                subproblem_id=str(m.get("subproblem_id")),
                rationale=m.get("rationale"),
            )
        )

    meta = dict(metadata or {})
    return MNode(
        source_problem_id=qnode_id,
        kind="analysis",
        function_blocks=function_blocks,
        subproblems=subproblems,
        dag_links=dag_links,
        block_to_subproblem=block_to_subproblem,
        requirements=[str(x) for x in requirements] if requirements else [],
        error_experiences=[],
        node_id=None,
        metadata=meta,
    )


def contrast_mnode_from_logic_contrast(
    qnode_id: str,
    analysis_function_blocks: List[FunctionBlock],
    *,
    incorrect_index: int,
    logic_contrast: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> MNode:
    """One **contrast** M-node from ``logic_contrast`` JSON (+ analysis blocks for MS mirroring)."""
    exp = ErrorExperience.new(
        incorrect_sol_id=f"inc_{incorrect_index}",
        block_differences=[
            BlockDifference(
                block_name=bd.get("block_name"),
                subproblem_name=bd.get("subproblem_name"),
                error_type=str(bd.get("error_type", "")),
                error_analysis=str(bd.get("error_analysis", "")),
                correct_rationale=str(bd.get("correct_rationale", "")),
                prevention_guideline=str(bd.get("prevention_guideline", "")),
            )
            for bd in (logic_contrast.get("block_differences") or [])
        ],
        global_diagnosis=logic_contrast.get("global_diagnosis"),
        requirements=logic_contrast.get("requirements", []) or [],
    )

    block_names = [
        (bd.block_name or "").strip()
        for bd in exp.block_differences
        if (bd.block_name or "").strip()
    ]
    seen_names: set[str] = set()
    contrast_blocks: List[FunctionBlock] = []
    for bname in block_names:
        if bname in seen_names:
            continue
        seen_names.add(bname)
        src_block = next((b for b in analysis_function_blocks if b.name_or_label == bname), None)
        if src_block is None:
            continue
        contrast_blocks.append(
            FunctionBlock(
                id=src_block.id,
                name_or_label=src_block.name_or_label,
                role=src_block.role,
                tags=list(src_block.tags),
                code=src_block.code,
                metadata={**(src_block.metadata or {}), "copied_from_analysis": "true"},
            )
        )

    meta = dict(metadata or {})
    meta["incorrect_index"] = incorrect_index

    return MNode(
        source_problem_id=qnode_id,
        kind="contrast",
        incorrect_index=incorrect_index,
        function_blocks=contrast_blocks,
        subproblems=[],
        dag_links=[],
        block_to_subproblem=[],
        requirements=[str(x) for x in (logic_contrast.get("requirements", []) or [])],
        error_experiences=[exp],
        node_id=None,
        metadata=meta,
    )
