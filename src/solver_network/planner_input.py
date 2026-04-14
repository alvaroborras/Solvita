"""
Build :class:`skill_graph.inference.PlannerInput` for skill-graph rollout.

Aligned with ``skill_graph_train.pipeline.build_planner_input`` (training episodes):
same ``description`` / ``similarity_description`` / tag channels so retrieval matches
the solver training code path.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from skill_graph.inference import PlannerInput


def canonical_text_for_similarity(canonical: Dict[str, Any]) -> str:
    """
    Flatten planner ``canonical_problem`` for the semantic similarity channel (vs ``QNode.abstract_description``).
    Mirrors ``skill_graph_train.pipeline.canonical_text_for_similarity``.
    """
    if not canonical:
        return ""
    parts: List[str] = []
    o = canonical.get("objective")
    if o:
        parts.append(f"Objective: {o}")
    for key in ("inputs", "outputs", "constraints"):
        v = canonical.get(key)
        if v:
            try:
                parts.append(f"{key}: {json.dumps(v, ensure_ascii=False)[:4000]}")
            except (TypeError, ValueError):
                parts.append(f"{key}: {v!s}"[:4000])
    rp = canonical.get("required_properties")
    if rp:
        parts.append(f"Required properties: {rp!s}"[:2000])
    ec = canonical.get("edge_cases")
    if ec:
        parts.append(f"Edge cases: {ec!s}"[:2000])
    return "\n".join(parts).strip()


def _tags_from_algorithm_choice(algorithm_choice: str) -> List[str]:
    """Fallback tag tokens from ``algorithm_choice`` when no level-1 tags are set (training-style)."""
    if not algorithm_choice or not isinstance(algorithm_choice, str):
        return ["unknown"]
    parts = re.split(r"[^\w]+", algorithm_choice.lower())
    out = [p for p in parts if len(p) >= 2][:12]
    return out or ["unknown"]


def build_planner_input_from_state(state: Dict[str, Any]) -> PlannerInput:
    """
    Runtime planner payload after ``abstract_problem_node`` (replaces training's ``plan_solution`` + record tags).

    - ``description``: objective + raw statement when objective exists (same as training).
    - ``similarity_description``: structured canonical text, else raw description.
    - ``similarity_tags``: level-1 ``tags_selected`` (up to 24), else tokens from ``algorithm_choice``.
    - ``tags``: same list as training's ``tag_row`` when tags exist, else algorithm-choice tokens.
    """
    raw_desc = (state.get("problem") or {}).get("description", "") or ""
    canonical = (state.get("problem") or {}).get("canonical", {}) or {}
    objective = canonical.get("objective", "")
    desc = f"{objective}\n\n{raw_desc}".strip() if objective else str(raw_desc).strip()

    direction = (state.get("plan") or {}).get("algorithm_choice", "") or ""

    raw_tags = (state.get("problem") or {}).get("tags_selected") or []
    if isinstance(raw_tags, str) and raw_tags.strip():
        tags_l1 = [raw_tags.strip().lower()]
    elif isinstance(raw_tags, list):
        tags_l1 = [str(t).strip().lower() for t in raw_tags if str(t).strip()]
    else:
        tags_l1 = []

    if tags_l1:
        tag_row = tags_l1
    else:
        tag_row = _tags_from_algorithm_choice(str(direction))

    sim_desc = canonical_text_for_similarity(canonical)
    if not (sim_desc or "").strip():
        sim_desc = str(raw_desc).strip()

    sim_tags_list = tags_l1[:24]
    if not sim_tags_list:
        sim_tags_list = [str(t).strip().lower() for t in tag_row if str(t).strip()][:24]

    return PlannerInput(
        description=desc,
        tags=list(tag_row),
        direction=str(direction),
        similarity_description=sim_desc,
        similarity_tags=list(sim_tags_list),
    )
