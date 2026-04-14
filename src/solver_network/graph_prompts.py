"""Format skill-graph augmentation for LLM prompts (English-only strings)."""

from __future__ import annotations

from typing import Dict, List, Sequence

from skill_graph.graph import SolvitaSkillGraph
from skill_graph.inference import SolverAugmentation
from skill_graph.nodes import QNode
from skill_graph.path_scoring import SkillPathContribution
from skill_graph.types import NodeId


def _q_raw_description(q: QNode) -> str:
    meta = getattr(q, "metadata", None) or {}
    if isinstance(meta, dict):
        return str(meta.get("description", "") or "").strip()
    return ""


def format_similar_q_nodes_for_codegen(q_nodes: List[QNode], *, max_items: int = 4) -> str:
    if not q_nodes:
        return "(none)"
    lines: List[str] = []
    sol_cap = 3500
    desc_cap = 2500
    abs_cap = 2000
    for q in q_nodes[:max_items]:
        pid = (getattr(q, "problem_id", None) or "") or q.node_id
        raw_full = _q_raw_description(q)
        if not raw_full:
            raw = "— (description not stored separately)"
        else:
            raw = raw_full[:desc_cap] + ("…" if len(raw_full) > desc_cap else "")
        abstract = (q.abstract_description or "").strip() or "—"
        if len(abstract) > abs_cap:
            abstract = abstract[:abs_cap] + "…"
        sol = ""
        if q.correct_solutions:
            sol = (q.correct_solutions[0] or "").strip()
        if sol:
            if len(sol) > sol_cap:
                sol = sol[:sol_cap] + "\n... (truncated)"
            sol_block = f"```\n{sol}\n```"
        else:
            sol_block = "— (no correct solution stored on this Q-node)"
        lines.append(f"#### Similar problem `problem_id={pid!r}` (graph Q `{q.node_id}`)")
        lines.append(f"- **Description:** {raw}")
        lines.append(f"- **Abstract:** {abstract}")
        lines.append("- **One correct solution:**")
        lines.append(sol_block)
    return "\n".join(lines)


def format_skill_augmentation(
    aug: SolverAugmentation,
    *,
    include_required_skill_templates: bool = True,
) -> str:
    has_skill_section = bool(
        include_required_skill_templates and aug.required_skills
    )
    parts: List[str] = []
    parts.append("## Skill graph context (auxiliary evidence only)\n")
    if has_skill_section:
        parts.append(
            "You must still solve the **current** problem statement exactly. "
            "Below: (1) similar problems from the graph, (2) why correct approaches work, "
            "(3) reference skills (templates + policy weight), (4) how others failed—use (4) to **avoid** mistakes.\n"
        )
    else:
        parts.append(
            "You must still solve the **current** problem statement exactly. "
            "Below: (1) similar problems from the graph, (2) why correct analysis approaches work, "
            "(3) how others failed on contrast runs—use (3) to **avoid** mistakes.\n"
        )

    if aug.source_q_nodes:
        parts.append("### 1. Similar problems in the graph (high similarity to your task)")
        parts.append(
            "For each neighbor Q we only include: **raw description**, **abstract**, and **one correct solution** "
            "(if stored on the node). Use lightly as analogy; your **current** problem statement and limits are authoritative.\n"
        )
        parts.append(format_similar_q_nodes_for_codegen(aug.source_q_nodes))
        parts.append("")

    if aug.subproblems:
        parts.append("### 2. From **analysis** M-nodes — why a correct solution works")
        parts.append(
            "The following comes from **analysis** subgraphs (positive, correct-solution logic chains). "
            "Focus on **why** the decomposition and steps are **sound**.\n"
        )
        for sp in aug.subproblems[:14]:
            parts.append(f"- {sp.description}")
        parts.append("")

    if has_skill_section:
        parts.append("### 3. Selected skills (reference templates + policy weight)")
        for i, rec in enumerate(aug.required_skills[:15], 1):
            s = rec.skill
            tmpl = (s.code_template or "").strip()
            if len(tmpl) > 1200:
                tmpl = tmpl[:1200] + "\n... (truncated)"
            conf = rec.confidence
            blocks = rec.contributing_blocks
            blk = f" [contributing M-blocks: {blocks}]" if blocks else ""
            parts.append(f"{i}. **{s.title}** (weight≈{conf:.6f}){blk}")
            if s.description:
                parts.append(f"   - {s.description}")
            if tmpl:
                parts.append("   ```cpp")
                parts.extend("   " + ln for ln in tmpl.splitlines()[:40])
                parts.append("   ```")
        parts.append("")

    contrast_idx = 4 if has_skill_section else 3
    if aug.error_warnings:
        parts.append(f"### {contrast_idx}. From **contrast** M-nodes — pitfalls to avoid")
        parts.append(
            "The following comes from **contrast** subgraphs (correct vs incorrect solution comparisons). "
            "Use it to **steer away** from known wrong reasoning.\n"
        )
        for ex in aug.error_warnings[:10]:
            diag = getattr(ex, "global_diagnosis", None) or ""
            reqs = getattr(ex, "requirements", None) or []
            req_s = "; ".join(str(x) for x in reqs[:4]) if reqs else ""
            parts.append(f"- **Diagnosis:** {diag}" + (f"\n  - **What was missing/wrong:** {req_s}" if req_s else ""))
        parts.append("")

    return "\n".join(parts)


def format_enriched_path_context(
    graph: SolvitaSkillGraph,
    best_path_per_skill: Dict[NodeId, SkillPathContribution],
    pi: Dict[NodeId, float],
    skill_ids: Sequence[str],
    *,
    section_index: int = 5,
) -> str:
    lines: List[str] = [
        f"### {section_index}. Path-level grounding (selected skills; scores for training)",
        "Each line is one high-scoring path Q→M→block→skill. "
        "**analysis** paths: positive structural support. **contrast** paths: remember to **avoid** the associated failure modes.\n",
    ]
    for sid in skill_ids:
        sid = str(sid)
        p = best_path_per_skill.get(sid)
        if p is None:
            lines.append(f"- **{sid}**: (no best path in subgraph)")
            continue
        qn = graph.q_nodes.get(p.q_node_id)
        mn = graph.m_nodes.get(p.m_node_id)
        m_kind = (getattr(mn, "kind", "") or "analysis").lower()
        if m_kind == "contrast":
            role_hint = (
                "**Contrast M:** this edge reflects lessons from wrong vs right comparisons—use only to **avoid** pitfalls, "
                "not as a template to copy."
            )
        else:
            role_hint = (
                "**Analysis M:** this edge reflects **why** a correct decomposition/solution works—use as positive structural guidance."
            )

        q_pid = getattr(qn, "problem_id", "") if qn else ""
        q_abs = (qn.abstract_description or "").strip() if qn else ""
        if len(q_abs) > 220:
            q_abs = q_abs[:220] + "…"

        blk_txt = ""
        if mn:
            blk = mn.get_block(p.block_id)
            if blk:
                blk_txt = (blk.name_or_label or blk.role or blk.block_id or "")[:160]

        p_pi = float(pi.get(sid, 0.0))
        lines.append(
            f"- **Skill `{sid}`**  π={p_pi:.6f}  path_score={p.path_score:.6f}  "
            f"(Sim={p.sim:.4f} w_qm={p.w_qm:.4f} w_ms={p.w_ms:.4f})"
        )
        lines.append(f"  - {role_hint}")
        lines.append(
            f"  - Path Q: `{p.q_node_id}`"
            + (f" problem_id={q_pid!r}" if q_pid else "")
            + f" abstract_snip={q_abs!r}"
        )
        lines.append(f"  - M `{p.m_node_id}` kind={m_kind!r} block={p.block_id!r} {blk_txt!r}")
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""
