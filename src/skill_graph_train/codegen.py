"""Single-shot initial C++ generation with optional skill-graph prompt block (training loop)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import logging

logger = logging.getLogger(__name__)

from skill_graph_train.bootstrap import ensure_import_paths

ensure_import_paths()

from src.llm import UnifiedLLMClient  # noqa: E402
from src.nodes.generate_code import (  # noqa: E402
    _build_initial_prompt,
    _format_abstract_tags_level2_block,
)
from src.utils.problem_utils import extract_problem_code  # noqa: E402
from src.utils.cpp_execution import sanitize_cpp  # noqa: E402
from skill_graph_train.prompts import format_skill_selection_subproblem_dag  # noqa: E402


def build_initial_prompt_with_skills(
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    constraints: Dict[str, Any],
    public_tests: List[Dict],
    generated_tests: List[Dict],
    memory_advice: str = "",
    skill_graph_block: str = "",
    compact: bool = False,
    *,
    abstract_tags_level2_block: str = "",
    skill_selection_skills_content: str = "",
    skill_selection_skill_ids_fallback: Optional[Sequence[str]] = None,
    skill_selection_dag_body: str = "",
    include_skill_selection_section: bool = True,
) -> str:
    """
    ``_build_initial_prompt`` plus optional skill-graph and skill-selection sections appended.

    ``skill_graph_block`` bundles similar-Q context, selected skills, path grounding, etc.
    """
    extra = ""
    if include_skill_selection_section:
        if skill_selection_skills_content.strip():
            extra += "\n\n### Selected skill references\n" + skill_selection_skills_content.strip()
        ids = list(skill_selection_skill_ids_fallback or [])
        if ids:
            extra += "\n\n### Selected skill ids (verbatim)\n" + "\n".join(str(x) for x in ids[:32])
        if skill_selection_dag_body.strip():
            extra += "\n\n" + skill_selection_dag_body.strip()
    combined_solver = ((skill_graph_block or "").strip() + extra).strip()
    base = _build_initial_prompt(
        problem_desc,
        algorithm,
        steps,
        constraints,
        public_tests,
        generated_tests,
        memory_advice=memory_advice,
        compact=compact,
        solver_graph_block=combined_solver if combined_solver else "",
        abstract_tags_level2_block=abstract_tags_level2_block,
    )
    return base


def generate_initial_cpp(
    state: Dict[str, Any],
    skill_graph_block: str = "",
    compile_feedback: str = "",
    *,
    include_skill_selection_in_prompt: bool = True,
) -> tuple[str, int]:
    """
    One LLM call: initial full solution (no SEARCH/REPLACE loop).

    Returns ``(code, llm_calls)``.
    """
    code_config = UnifiedLLMClient.build_role_config(state["config"], "solver_codegen")
    llm = UnifiedLLMClient(code_config)

    if not include_skill_selection_in_prompt:
        problem_desc = state["problem"].get("description", "")
    else:
        canonical = state["problem"].get("canonical", {})
        if canonical:
            problem_desc = f"""Objective: {canonical.get('objective', '')}
Inputs: {json.dumps(canonical.get('inputs', {}), indent=2)}
Outputs: {json.dumps(canonical.get('outputs', {}), indent=2)}
Constraints: {json.dumps(canonical.get('constraints', {}), indent=2)}
Required Properties: {canonical.get('required_properties', [])}"""
        else:
            problem_desc = state["problem"].get("description", "")

    plan = state.get("plan") or {}
    algorithm = "" if not include_skill_selection_in_prompt else (plan.get("algorithm_choice", "") or "")
    steps = [] if not include_skill_selection_in_prompt else (plan.get("implementation_steps") or [])
    constraints = state["problem"].get("constraints", {})
    public_tests = state["problem"].get("public_tests", [])
    generated_tests = [] if not include_skill_selection_in_prompt else (
        state.get("tests", {}).get("generated_tests", []) or []
    )

    tags_l2 = state.get("problem", {}).get("tags_level2_selected") or []
    if isinstance(tags_l2, str):
        tags_l2_list: List[str] = [tags_l2] if tags_l2.strip() else []
    elif isinstance(tags_l2, list):
        tags_l2_list = [str(t).strip() for t in tags_l2 if str(t).strip()]
    else:
        tags_l2_list = []
    abstract_tags_level2_block = (
        _format_abstract_tags_level2_block(tags_l2_list)
        if include_skill_selection_in_prompt
        else ""
    )

    if include_skill_selection_in_prompt:
        raw_sel = plan.get("skill_selection_skill_ids")
        if isinstance(raw_sel, str) and raw_sel.strip():
            skill_sel_ids: List[str] = [raw_sel.strip()]
        elif isinstance(raw_sel, list):
            skill_sel_ids = [str(x).strip() for x in raw_sel if str(x).strip()]
        else:
            skill_sel_ids = []

        skill_content_md = (plan.get("skill_selection_skills_content_md") or "").strip()

        dag_body = format_skill_selection_subproblem_dag(
            plan.get("skill_selection_subproblem_dag") or {},
            include_leading_heading=False,
        )
    else:
        skill_sel_ids = []
        skill_content_md = ""
        dag_body = ""

    prompt = build_initial_prompt_with_skills(
        problem_desc,
        algorithm,
        steps,
        constraints,
        public_tests,
        generated_tests,
        memory_advice="",
        skill_graph_block=skill_graph_block,
        compact=False,
        abstract_tags_level2_block=abstract_tags_level2_block,
        skill_selection_skills_content=skill_content_md,
        skill_selection_skill_ids_fallback=skill_sel_ids,
        skill_selection_dag_body=dag_body,
        include_skill_selection_section=include_skill_selection_in_prompt,
    )
    fb = (compile_feedback or "").strip()
    if fb:
        prompt += (
            "\n\n## Compiler / validator feedback (fix and output a complete C++ solution)\n"
            "The previous submission did not compile. Address these errors exactly:\n\n"
            + fb[:12000]
            + "\n\nOutput ONLY the fixed complete C++ source code.\n"
        )

    response = llm.generate(prompt)
    code = sanitize_cpp(response)
    logger.info(
        "[codegen] Generated %d chars, skill_block=%s",
        len(code),
        "yes" if (skill_graph_block or "").strip() else "no",
    )
    return code, 1


def attach_solution_to_state(state: Dict[str, Any], code: str) -> Dict[str, Any]:
    """Return patch for ``solution`` dict (version bump, no compile yet)."""
    version = state.get("solution", {}).get("version", 0) + 1
    problem_code = extract_problem_code(state.get("raw_problem", {}))
    if problem_code:
        out_dir = Path("data") / "generated" / problem_code / "code"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"solution_v{version}.cpp").write_text(code, encoding="utf-8")
        (out_dir / "solution_latest.cpp").write_text(code, encoding="utf-8")

    solution = {
        "code": code,
        "version": version,
        "compilation_success": False,
        "compilation_errors": [],
        "executable_path": None,
        "memory_item_ids": [],
    }
    return {"solution": solution}
