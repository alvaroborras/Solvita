import json
from typing import Any, Dict, List

from loguru import logger

from src.llm import UnifiedLLMClient
from src.nodes.generator_common import (
    apply_patch_response,
    parse_repair_checklist,
    render_input_validity_constraints,
    render_repair_checklist,
)
from src.utils.prompt_templates import render_template

SEARCH_MARKER = "<" * 7 + " SEARCH"
SEPARATOR_MARKER = "=" * 7
REPLACE_MARKER = ">" * 7 + " REPLACE"


def build_semantic_generator_prompt(
    problem_desc: str,
    constraints_text: str,
    analyst_report: Dict[str, Any],
    memory_advice: str = "",
    previous_attempt_issues: str = "",
    previous_generated_input: str = "",
) -> str:
    """
    Constructs the prompt instructing the LLM to write a targeted C++ Semantic Test Generator.
    """
    report_json = json.dumps(analyst_report, indent=2, ensure_ascii=False)

    advice_section = ""
    if memory_advice:
        advice_section = f"\n=== HACKER STRATEGY ADVICE ===\n{memory_advice}\n=============================\n"
    previous_issues_section = ""
    if previous_attempt_issues:
        previous_issues_section = f"\nPREVIOUS ATTEMPT ISSUES:\n{previous_attempt_issues}\n"
    previous_input_section = ""
    if previous_generated_input:
        previous_input_section = f"\nPREVIOUS GENERATED INPUT (truncated):\n{previous_generated_input}\n"

    return render_template(
        "hacker_generators.semantic.generator",
        PROBLEM_DESC=problem_desc,
        ADVICE_SECTION=advice_section,
        CONSTRAINTS_TEXT=constraints_text,
        PREVIOUS_ISSUES_SECTION=previous_issues_section,
        PREVIOUS_INPUT_SECTION=previous_input_section,
        REPORT_JSON=report_json,
    )


def build_semantic_checklist_prompt(
    problem_desc: str,
    constraints_text: str,
    analyst_report: Dict[str, Any],
    last_generator_code: str,
    failure_kind: str,
    failure_reason: str,
    previous_attempt_issues: str = "",
    previous_generated_input: str = "",
    memory_advice: str = "",
) -> str:
    report_json = json.dumps(analyst_report, indent=2, ensure_ascii=False)
    advice_section = f"\nHACKER STRATEGY ADVICE:\n{memory_advice}\n" if memory_advice else ""
    issues_section = f"\nACCUMULATED PREVIOUS ATTEMPT ISSUES:\n{previous_attempt_issues}\n" if previous_attempt_issues else ""
    input_section = f"\nPREVIOUS GENERATED INPUT (truncated):\n{previous_generated_input}\n" if previous_generated_input else ""

    return render_template(
        "hacker_generators.semantic.checklist",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_TEXT=constraints_text,
        ADVICE_SECTION=advice_section,
        FAILURE_KIND=failure_kind or "unknown",
        FAILURE_REASON=failure_reason or "unknown",
        ISSUES_SECTION=issues_section,
        INPUT_SECTION=input_section,
        REPORT_JSON=report_json,
        LAST_GENERATOR_CODE=last_generator_code,
    )


def build_semantic_patch_prompt(
    problem_desc: str,
    constraints_text: str,
    analyst_report: Dict[str, Any],
    last_generator_code: str,
    checklist: Dict[str, List[str]],
    failure_kind: str,
    failure_reason: str,
    previous_generated_input: str = "",
    memory_advice: str = "",
) -> str:
    report_json = json.dumps(analyst_report, indent=2, ensure_ascii=False)
    checklist_json = render_repair_checklist(checklist)
    advice_section = f"\nHACKER STRATEGY ADVICE:\n{memory_advice}\n" if memory_advice else ""
    input_section = f"\nPREVIOUS GENERATED INPUT (truncated):\n{previous_generated_input}\n" if previous_generated_input else ""
    patch_format = "\n".join(
        [
            SEARCH_MARKER,
            "exact old code",
            SEPARATOR_MARKER,
            "new code",
            REPLACE_MARKER,
        ]
    )

    return render_template(
        "hacker_generators.semantic.patch",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_TEXT=constraints_text,
        ADVICE_SECTION=advice_section,
        FAILURE_KIND=failure_kind or "unknown",
        FAILURE_REASON=failure_reason or "unknown",
        INPUT_SECTION=input_section,
        REPORT_JSON=report_json,
        CHECKLIST_JSON=checklist_json,
        LAST_GENERATOR_CODE=last_generator_code,
        PATCH_FORMAT=patch_format,
    )


def generate_semantic_test_program(
    state: Dict[str, Any],
    llm: UnifiedLLMClient,
    analyst_report: Dict[str, Any],
    memory_advice: str = "",
    previous_attempt_issues: str = "",
    previous_generated_input: str = "",
) -> str:
    """
    Invokes the LLM to generate the Semantic C++ Test Generator.
    """
    logger.info(f"[Semantic Generator] Targeting bug class '{analyst_report.get('bug_class')}'...")

    problem_desc = state.get("problem", {}).get("description", "")
    constraints_text = render_input_validity_constraints(state)

    prompt = build_semantic_generator_prompt(
        problem_desc,
        constraints_text,
        analyst_report,
        memory_advice=memory_advice,
        previous_attempt_issues=previous_attempt_issues,
        previous_generated_input=previous_generated_input[:400],
    )

    cpp_source = llm.generate(prompt)

    from src.utils.cpp_execution import sanitize_cpp

    try:
        clean_cpp = sanitize_cpp(cpp_source)
    except Exception as exc:
        logger.warning(f"[Semantic Generator] LLM produced invalid/dangerous format: {exc}")
        return "int main() { return 1; }"

    return clean_cpp


def repair_semantic_test_program(
    state: Dict[str, Any],
    llm: UnifiedLLMClient,
    analyst_report: Dict[str, Any],
    last_generator_code: str,
    failure_kind: str,
    failure_reason: str,
    previous_attempt_issues: str = "",
    previous_generated_input: str = "",
    memory_advice: str = "",
) -> str:
    """
    Repairs the previous Semantic generator via checklist + SEARCH/REPLACE patching.
    """
    if not last_generator_code:
        return generate_semantic_test_program(
            state,
            llm,
            analyst_report,
            memory_advice=memory_advice,
            previous_attempt_issues=previous_attempt_issues,
            previous_generated_input=previous_generated_input,
        )

    problem_desc = state.get("problem", {}).get("description", "")
    constraints_text = render_input_validity_constraints(state)

    checklist_prompt = build_semantic_checklist_prompt(
        problem_desc,
        constraints_text,
        analyst_report,
        last_generator_code=last_generator_code,
        failure_kind=failure_kind,
        failure_reason=failure_reason,
        previous_attempt_issues=previous_attempt_issues,
        previous_generated_input=previous_generated_input[:400],
        memory_advice=memory_advice,
    )
    checklist = parse_repair_checklist(
        llm.generate(checklist_prompt),
        fallback_reason=failure_reason or previous_attempt_issues,
    )

    patch_prompt = build_semantic_patch_prompt(
        problem_desc,
        constraints_text,
        analyst_report,
        last_generator_code=last_generator_code,
        checklist=checklist,
        failure_kind=failure_kind,
        failure_reason=failure_reason,
        previous_generated_input=previous_generated_input[:400],
        memory_advice=memory_advice,
    )
    patch_response = llm.generate(patch_prompt)

    ok, patched_cpp, patch_error = apply_patch_response(last_generator_code, patch_response)
    if not ok:
        logger.warning(f"[Semantic Generator] Patch application failed: {patch_error}")
        return last_generator_code

    from src.utils.cpp_execution import sanitize_cpp

    try:
        return sanitize_cpp(patched_cpp)
    except Exception as exc:
        logger.warning(f"[Semantic Generator] Patched code failed sanitation: {exc}")
        return last_generator_code
