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


def build_stress_generator_prompt(
    problem_desc: str,
    constraints_text: str,
) -> str:
    """
    Constructs the prompt instructing the LLM to write a high-throughput C++ Fuzzer.
    """
    return f"""You are the Stress Test Generator, a specialized C++ coder for an adversarial Hacker System.
Your job is to write a standalone C++ program (`int main()`) that acts as a high-throughput Fuzzer.

PROBLEM DESCRIPTION:
{problem_desc}

CONSTRAINTS (The output of your C++ fuzzer MUST strictly satisfy these boundaries):
{constraints_text}

INSTRUCTIONS FOR C++ FUZZER:
1. Write a complete, compilable C++17 program.
2. VALIDITY-FIRST: the generated input MUST pass the problem validator and explicitly enforce all structural constraints in code.
3. The program must print EXACTLY ONE valid test case to standard output, but this test case should be as LARGE and COMPLEX as the constraints allow.
4. You MUST use `<random>` and `std::mt19937_64` initialized with a random device or fixed seed.
5. Scale up the generation loop to approach the maximum `N`, `M`, or `K` allowed.
6. Emphasize boundary values (e.g. generating values alternating between min and max allowed).
7. Optimize the generator for speed using `\\n` instead of `std::endl` and fast I/O (`std::ios_base::sync_with_stdio(false);`).

CRITICAL FORMATTING RULES:
1. Return ONLY the C++ code.
2. DO NOT wrap the code in markdown blocks (e.g., ```cpp ... ```).
3. The very first line should be `#include <...>` or similar valid C++.

Write the C++ Stress Test Generator code now:
"""


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

    return f"""You are repairing a C++ Stress Test Generator after a failed attempt.
Analyze the failure and produce a compact JSON checklist before patching the code.

PROBLEM DESCRIPTION:
{problem_desc}

INPUT VALIDITY CONSTRAINTS:
{constraints_text}

LATEST FAILURE TYPE: {failure_kind or "unknown"}
LATEST FAILURE REASON:
{failure_reason or "unknown"}
{issues_section}
{input_section}
PREVIOUS GENERATOR CODE:
{last_generator_code}

CHECKLIST RULES:
1. VALIDITY BEFORE ATTACK: first restore validator-accepted input, then keep the case large and boundary-heavy.
2. `must_fix` must target the concrete compile/runtime/validator failure from the latest attempt.
3. `do_not_regress` must preserve constraints already satisfied by the generator.
4. `attack_goal` must keep the output large, high-throughput, and stress-oriented after repairs.
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

    return f"""You are applying a minimal patch to a C++ Stress Test Generator.
You must patch the existing generator with minimal SEARCH/REPLACE edits instead of rewriting it from scratch.

PROBLEM DESCRIPTION:
{problem_desc}

INPUT VALIDITY CONSTRAINTS:
{constraints_text}

LATEST FAILURE TYPE: {failure_kind or "unknown"}
LATEST FAILURE REASON:
{failure_reason or "unknown"}
{input_section}
REPAIR CHECKLIST:
{checklist_json}

CURRENT GENERATOR CODE:
{last_generator_code}

PATCH RULES:
1. VALIDITY-FIRST: fix the latest failure before increasing attack pressure.
2. Preserve already-correct large-case generation logic when possible.
3. Keep the generator large, randomized, and boundary-oriented after the repair.
4. Output only SEARCH/REPLACE blocks.
5. Each SEARCH block must match the current generator code exactly once.
6. Make the patch minimal and surgical. Do NOT replace the whole file.

Required patch format:
{patch_format}
"""


def generate_stress_test_program(
    state: Dict[str, Any],
    llm: UnifiedLLMClient,
) -> str:
    """
    Invokes the LLM to generate the Stress C++ Fuzzer.
    """
    logger.info("[Stress Generator] Generating boundary/randomized fallback Fuzzer...")

    problem_desc = state.get("problem", {}).get("description", "")
    constraints_text = render_input_validity_constraints(state)

    prompt = build_stress_generator_prompt(problem_desc, constraints_text)
    cpp_source = llm.generate(prompt)

    from src.utils.cpp_execution import sanitize_cpp

    try:
        clean_cpp = sanitize_cpp(cpp_source)
    except Exception as exc:
        logger.warning(f"[Stress Generator] LLM produced invalid/dangerous format: {exc}")
        return "int main() { return 1; }"

    return clean_cpp


def repair_stress_test_program(
    state: Dict[str, Any],
    llm: UnifiedLLMClient,
    last_generator_code: str,
    failure_kind: str,
    failure_reason: str,
    previous_attempt_issues: str = "",
    previous_generated_input: str = "",
) -> str:
    """
    Repairs the previous Stress generator via checklist + SEARCH/REPLACE patching.
    """
    if not last_generator_code:
        return generate_stress_test_program(state, llm)

    problem_desc = state.get("problem", {}).get("description", "")
    constraints_text = render_input_validity_constraints(state)

    checklist_prompt = build_stress_checklist_prompt(
        problem_desc,
        constraints_text,
        last_generator_code=last_generator_code,
        failure_kind=failure_kind,
        failure_reason=failure_reason,
        previous_attempt_issues=previous_attempt_issues,
        previous_generated_input=previous_generated_input[:400],
    )
    checklist = parse_repair_checklist(
        llm.generate(checklist_prompt),
        fallback_reason=failure_reason or previous_attempt_issues,
    )

    patch_prompt = build_stress_patch_prompt(
        problem_desc,
        constraints_text,
        last_generator_code=last_generator_code,
        checklist=checklist,
        failure_kind=failure_kind,
        failure_reason=failure_reason,
        previous_generated_input=previous_generated_input[:400],
    )
    patch_response = llm.generate(patch_prompt)

    ok, patched_cpp, patch_error = apply_patch_response(last_generator_code, patch_response)
    if not ok:
        logger.warning(f"[Stress Generator] Patch application failed: {patch_error}")
        return last_generator_code

    from src.utils.cpp_execution import sanitize_cpp

    try:
        return sanitize_cpp(patched_cpp)
    except Exception as exc:
        logger.warning(f"[Stress Generator] Patched code failed sanitation: {exc}")
        return last_generator_code
