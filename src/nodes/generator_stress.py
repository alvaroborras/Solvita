from typing import Any, Dict, List, Tuple

from loguru import logger

from src.llm import UnifiedLLMClient
from src.nodes._chat_utils import chat_with_history
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


def build_stress_generator_prompt(
    problem_desc: str,
    constraints_text: str,
) -> str:
    """
    Constructs the prompt instructing the LLM to write a high-throughput C++ Fuzzer.
    """
    return render_template(
        "hacker_generators.stress.generator",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_TEXT=constraints_text,
    )


def build_stress_checklist_prompt(
    problem_desc: str,
    constraints_text: str,
    last_generator_code: str,
    failure_kind: str,
    failure_reason: str,
    previous_attempt_issues: str = "",
    previous_generated_input: str = "",
) -> str:
    issues_section = f"\nACCUMULATED PREVIOUS ATTEMPT ISSUES:\n{previous_attempt_issues}\n" if previous_attempt_issues else ""
    input_section = f"\nPREVIOUS GENERATED INPUT (truncated):\n{previous_generated_input}\n" if previous_generated_input else ""

    return render_template(
        "hacker_generators.stress.checklist",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_TEXT=constraints_text,
        FAILURE_KIND=failure_kind or "unknown",
        FAILURE_REASON=failure_reason or "unknown",
        ISSUES_SECTION=issues_section,
        INPUT_SECTION=input_section,
        LAST_GENERATOR_CODE=last_generator_code,
    )


def build_stress_patch_prompt(
    problem_desc: str,
    constraints_text: str,
    last_generator_code: str,
    checklist: Dict[str, List[str]],
    failure_kind: str,
    failure_reason: str,
    previous_generated_input: str = "",
) -> str:
    checklist_json = render_repair_checklist(checklist)
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
        "hacker_generators.stress.patch",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_TEXT=constraints_text,
        FAILURE_KIND=failure_kind or "unknown",
        FAILURE_REASON=failure_reason or "unknown",
        INPUT_SECTION=input_section,
        CHECKLIST_JSON=checklist_json,
        LAST_GENERATOR_CODE=last_generator_code,
        PATCH_FORMAT=patch_format,
    )


def generate_stress_test_program(
    state: Dict[str, Any],
    llm: UnifiedLLMClient,
    messages_history: list = None,
) -> Tuple[str, List[Dict[str, str]]]:
    """Returns (cpp_source, new_messages)."""
    logger.info("[Stress Generator] Generating boundary/randomized fallback Fuzzer...")

    problem_desc = state.get("problem", {}).get("description", "")
    constraints_text = render_input_validity_constraints(state)

    prompt = build_stress_generator_prompt(problem_desc, constraints_text)
    history = list(messages_history) if messages_history else []
    cpp_source, new_msgs = chat_with_history(llm, history, prompt)

    from src.utils.cpp_execution import sanitize_cpp

    try:
        clean_cpp = sanitize_cpp(cpp_source)
    except Exception as exc:
        logger.warning(f"[Stress Generator] LLM produced invalid/dangerous format: {exc}")
        return "int main() { return 1; }", new_msgs

    return clean_cpp, new_msgs


def repair_stress_test_program(
    state: Dict[str, Any],
    llm: UnifiedLLMClient,
    last_generator_code: str,
    failure_kind: str,
    failure_reason: str,
    previous_attempt_issues: str = "",
    previous_generated_input: str = "",
    messages_history: list = None,
) -> Tuple[str, List[Dict[str, str]]]:
    """Returns (cpp_source, new_messages)."""
    if not last_generator_code:
        return generate_stress_test_program(state, llm, messages_history=messages_history)

    problem_desc = state.get("problem", {}).get("description", "")
    constraints_text = render_input_validity_constraints(state)
    history = list(messages_history) if messages_history else []
    all_new_msgs: List[Dict[str, str]] = []

    checklist_prompt = build_stress_checklist_prompt(
        problem_desc, constraints_text,
        last_generator_code=last_generator_code,
        failure_kind=failure_kind, failure_reason=failure_reason,
        previous_attempt_issues=previous_attempt_issues,
        previous_generated_input=previous_generated_input[:400],
    )
    checklist_response, new_msgs = chat_with_history(llm, history, checklist_prompt)
    all_new_msgs.extend(new_msgs)
    history.extend(new_msgs)
    checklist = parse_repair_checklist(checklist_response, fallback_reason=failure_reason or previous_attempt_issues)

    patch_prompt = build_stress_patch_prompt(
        problem_desc, constraints_text,
        last_generator_code=last_generator_code, checklist=checklist,
        failure_kind=failure_kind, failure_reason=failure_reason,
        previous_generated_input=previous_generated_input[:400],
    )
    patch_response, new_msgs = chat_with_history(llm, history, patch_prompt)
    all_new_msgs.extend(new_msgs)

    ok, patched_cpp, patch_error = apply_patch_response(last_generator_code, patch_response)
    if not ok:
        logger.warning(f"[Stress Generator] Patch application failed: {patch_error}")
        return last_generator_code, all_new_msgs

    from src.utils.cpp_execution import sanitize_cpp

    try:
        return sanitize_cpp(patched_cpp), all_new_msgs
    except Exception as exc:
        logger.warning(f"[Stress Generator] Patched code failed sanitation: {exc}")
        return last_generator_code, all_new_msgs
