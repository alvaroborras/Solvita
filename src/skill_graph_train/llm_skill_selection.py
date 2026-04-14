"""
Skill selection LLM step — re-exports the canonical implementation used at runtime.

The single source of truth is ``src.solver_network.llm_skill_selection`` (prompts in
``config/prompt_template.yaml`` under ``solver_skill_selection``).
"""

from __future__ import annotations

from src.solver_network.llm_skill_selection import (  # noqa: F401
    SkillSelectionResult,
    llm_select_skills,
    normalize_subproblem_dag,
    parse_selected_skill_ids,
    parse_selected_skill_ids_with_fallback,
    parse_skill_selection_response,
    subproblem_dag_nonempty,
    topk_skills_by_rho,
)

__all__ = [
    "SkillSelectionResult",
    "llm_select_skills",
    "normalize_subproblem_dag",
    "parse_selected_skill_ids",
    "parse_selected_skill_ids_with_fallback",
    "parse_skill_selection_response",
    "subproblem_dag_nonempty",
    "topk_skills_by_rho",
]
