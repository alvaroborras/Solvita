"""Training-only: format skill-selection subproblem DAG for codegen prompts."""

from __future__ import annotations

from typing import Any, Dict


def format_skill_selection_subproblem_dag(
    dag: Dict[str, Any],
    *,
    include_leading_heading: bool = True,
) -> str:
    """
    Render the sub-problem DAG from the skill-selection LLM for the codegen prompt.

    Shape: ``{"nodes": [{"id": str, "description": str}, ...], "edges": [{"from_id", "to_id"}, ...]}``.

    When ``include_leading_heading`` is False, omit the top ``##`` title so the caller can embed this
    block under its own section.
    """
    if not isinstance(dag, dict):
        return ""
    nodes = dag.get("nodes") or []
    edges = dag.get("edges") or []
    if not nodes and not edges:
        return ""
    intro = (
        "The model decomposed the **current** problem into abstract sub-goals. "
        "Respect dependency order: an edge from_id → to_id means **from_id** must be resolved before **to_id**. "
        "Implement the full solution consistent with this DAG.\n"
    )
    parts: list[str] = []
    if include_leading_heading:
        parts.extend(["## Sub-problem DAG (skill-selection step)", intro])
    else:
        parts.append(intro)
    if nodes:
        parts.append("### DAG nodes")
        for n in nodes[:48]:
            if isinstance(n, dict):
                nid = str(n.get("id", "") or "").strip() or "?"
                desc = str(n.get("description", "") or "").strip()
                if len(desc) > 600:
                    desc = desc[:600] + "…"
                parts.append(f"- `{nid}`: {desc}")
            else:
                parts.append(f"- {n!s}")
        parts.append("")
    if edges:
        parts.append("### DAG edges (dependencies)")
        for e in edges[:96]:
            if isinstance(e, dict):
                fi = str(e.get("from_id", e.get("from", "")) or "").strip()
                ti = str(e.get("to_id", e.get("to", "")) or "").strip()
                parts.append(f"- `{fi}` → `{ti}`")
            else:
                parts.append(f"- {e!s}")
        parts.append("")
    return "\n".join(parts).strip()
