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

    return f"""You are the Semantic Generator, a specialized C++ coder for an adversarial Hacker System.
Your job is to write a standalone C++ program that generates a single, highly-targeted test case designed to trigger the specific vulnerability described by the Code Analyst.

PROBLEM DESCRIPTION:
{problem_desc}
{advice_section}
CONSTRAINTS (The output of your C++ generator MUST satisfy ALL of these):
{constraints_text}
{previous_issues_section}
{previous_input_section}

VULNERABILITY REPORT (from Code Analyst):
{report_json}

INSTRUCTIONS FOR C++ GENERATOR:
1. Write a complete, compilable C++17 program (`int main() {{...}}`).
2. The program must print EXACTLY ONE valid test case to standard output (`std::cout`).
3. VALIDITY-FIRST: the generated input MUST satisfy all format and validator constraints before you try to make it adversarial.
4. Focus on producing the input data structures matching the `input_hypothesis` in the report.
5. If the previous attempt was rejected, fix those exact issues before changing anything else.
6. DO NOT use uninitialized variables or undefined behavior in your generator.
7. If you need randomness, you MAY use `<random>` (`std::mt19937`), but since this is the Semantic Generator, deterministic construction of the edge case is preferred when possible.

CRITICAL FORMATTING RULES:
1. Return ONLY the C++ code.
2. DO NOT wrap the code in markdown blocks (e.g., ```cpp ... ```).
3. The very first line should be `#include <...>` or similar valid C++.

Write the C++ generator code now:
"""


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

    return f"""You are repairing a C++ Semantic Generator after a failed attack-input attempt.
Analyze the failure and produce a compact JSON checklist before patching the code.

PROBLEM DESCRIPTION:
{problem_desc}

INPUT VALIDITY CONSTRAINTS:
{constraints_text}
{advice_section}
LATEST FAILURE TYPE: {failure_kind or "unknown"}
LATEST FAILURE REASON:
{failure_reason or "unknown"}
{issues_section}
{input_section}
VULNERABILITY REPORT:
{report_json}

PREVIOUS GENERATOR CODE:
{last_generator_code}

CHECKLIST RULES:
1. VALIDITY BEFORE ATTACK: first restore validator-accepted input, then preserve adversarial intent.
2. `must_fix` must focus on the concrete compile/runtime/validator issue from the latest failure.
3. `do_not_regress` must list already-required legality properties that must remain true.
4. `attack_goal` must keep the attack aligned with the analyst report instead of collapsing into trivial valid input.
5. Be failure-type aware:
   - compile_failed -> prioritize syntax/API/build repairs
   - validator_rejected -> prioritize legality/format repairs
   - runtime_error -> prioritize execution safety
   - empty_output -> prioritize guaranteed emission of one valid case

Return ONLY valid JSON with exactly this schema:
{{
  "must_fix": ["..."],
  "do_not_regress": ["..."],
  "attack_goal": ["..."]
}}
"""


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

    return f"""You are applying a minimal patch to a C++ Semantic Generator.
You must patch the existing generator with minimal SEARCH/REPLACE edits instead of rewriting it from scratch.

PROBLEM DESCRIPTION:
{problem_desc}

INPUT VALIDITY CONSTRAINTS:
{constraints_text}
{advice_section}
LATEST FAILURE TYPE: {failure_kind or "unknown"}
LATEST FAILURE REASON:
{failure_reason or "unknown"}
{input_section}
VULNERABILITY REPORT:
{report_json}

REPAIR CHECKLIST:
{checklist_json}

CURRENT GENERATOR CODE:
{last_generator_code}

PATCH RULES:
1. VALIDITY-FIRST: fix the latest failure before any attack refinement.
2. Preserve already-correct code whenever possible.
3. Keep the attack goal from the checklist after legality is restored.
4. Output only SEARCH/REPLACE blocks.
5. Each SEARCH block must match the current generator code exactly once.
6. Make the patch minimal and surgical. Do NOT replace the whole file.

Required patch format:
{patch_format}
"""


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
