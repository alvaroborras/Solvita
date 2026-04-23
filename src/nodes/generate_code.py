"""Generate Code Node - Generate C++ solution code with lightweight self-validation"""

import json
import tempfile
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from loguru import logger
from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.nodes._chat_utils import build_chat_compaction_context, chat_with_history, normalize_chat_history_result
from src.utils.cpp_execution import (
    sanitize_cpp,
    compile_cpp,
    run_program,
    ExecutionLimits,
    cleanup_tempdir,
)
from src.utils.output_judging import judge_output_against_certified_expected
from src.utils.json_utils import parse_json_response
from src.utils.patch_utils import parse_search_replace_blocks, apply_search_replace_blocks, compute_unified_diff
from src.memory import MemoryClient, MemoryNamespace
from src.utils.problem_utils import extract_problem_code
from src.utils.prompt_utils import compact_json_for_prompt, truncate_for_prompt
from src.utils.prompt_templates import get_nested_template, load_prompt_templates, render_placeholders, render_template
from src.solver_network.adapter import build_solver_network_block


def _format_abstract_tags_level2_block(tags: List[str]) -> str:
    """Optional fine-grained tags from abstract_problem (prompt-only; not for skill-graph Jaccard)."""
    if not tags:
        return ""
    return (
        "Fine-grained tag hints (optional; not used for retrieval):\n"
        + ", ".join(tags)
        + "\n"
    )


def _build_initial_prompt(
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    constraints: Dict[str, Any],
    public_tests: List[Dict],
    generated_tests: List[Dict],
    memory_advice: str = "",
    compact: bool = False,
    solver_graph_block: str = "",
    abstract_tags_level2_block: str = "",
    self_validation_feedback: str = "",
) -> str:
    """Build prompt for initial code generation (no previous code)."""
    desc_chars = 10000 if not compact else 5000
    constraint_chars = 2500 if not compact else 1200
    generated_chars = 300 if not compact else 150
    public_chars = 400 if not compact else 180
    problem_desc = truncate_for_prompt(problem_desc, desc_chars, "PROBLEM_DESC")

    public_block = ""
    if public_tests:
        parts = []
        for i, t in enumerate(public_tests[:3]):
            sample_input = truncate_for_prompt(t.get('input', ''), public_chars, f"PUBLIC_INPUT_{i+1}")
            sample_output = truncate_for_prompt(t.get('output', ''), public_chars, f"PUBLIC_OUTPUT_{i+1}")
            parts.append(f"  Sample {i+1}:")
            parts.append(f"    Input:\n{_indent(sample_input, 6)}")
            parts.append(f"    Output:\n{_indent(sample_output, 6)}")
        public_block = "Public test cases:\n" + "\n".join(parts)

    constraints_block = ""
    if constraints:
        constraints_block = f"Constraints:\n  {compact_json_for_prompt(constraints, constraint_chars, 'CONSTRAINTS')}"

    gen_block = ""
    if generated_tests:
        samples = generated_tests[:3]
        parts = []
        for i, t in enumerate(samples):
            inp = t.get("input", "").strip()
            if len(inp) > generated_chars:
                inp = inp[:generated_chars] + "...(truncated)"
            parts.append(f"  Generated input {i+1}:\n{_indent(inp, 4)}")
        gen_block = (
            "Sample generated inputs (for format/scale reference):\n"
            + "\n".join(parts)
        )

    memory_block = f"\n{memory_advice}\n" if memory_advice else ""
    self_validation_block = f"\n{self_validation_feedback.strip()}\n" if self_validation_feedback.strip() else ""
    solver_section = ""
    if (solver_graph_block or "").strip():
        solver_section = solver_graph_block.strip() + "\n\n"

    templates = load_prompt_templates()
    tpl = get_nested_template(templates, "generate_code.initial")
    if not isinstance(tpl, str):
        raise KeyError("generate_code.initial must be a string template")

    steps_block = "\n".join(steps)
    return render_placeholders(
        tpl,
        {
            "PROBLEM_DESC": problem_desc,
            "ABSTRACT_TAGS_LEVEL2_BLOCK": abstract_tags_level2_block,
            "ALGORITHM": algorithm,
            "STEPS": steps_block,
            "CONSTRAINTS_BLOCK": constraints_block,
            "PUBLIC_BLOCK": public_block,
            "GEN_BLOCK": gen_block,
            "SOLVER_GRAPH_BLOCK": solver_section,
            "SELF_VALIDATION_BLOCK": self_validation_block,
            "MEMORY_ADVICE": memory_block,
        },
    )


def _build_patch_prompt(
    prev_code: str,
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    specific_failures: List[Dict],
    suggested_fixes: List[str],
    feedback_text: str,
    aggregate_failures_text: str = "",
    memory_advice: str = "",
    compact: bool = False,
    abstract_tags_level2_block: str = "",
) -> str:
    """Build prompt for patching existing code using SEARCH/REPLACE."""
    prev_code = truncate_for_prompt(prev_code, 16000 if not compact else 8000, "PREV_CODE")
    problem_desc = truncate_for_prompt(problem_desc, 9000 if not compact else 4500, "PROBLEM_DESC")
    feedback_text = truncate_for_prompt(feedback_text, 5000 if not compact else 2000, "FEEDBACK_TEXT")
    aggregate_failures_text = truncate_for_prompt(
        aggregate_failures_text,
        4000 if not compact else 1600,
        "AGGREGATE_FAILURES_TEXT",
    )

    failures_block = ""
    if specific_failures:
        parts = ["The following test cases are FAILING:"]
        for i, fail in enumerate(specific_failures[:10]):
            parts.append(f"\nFailure {i+1} ({fail.get('type', 'Unknown Error')}):")
            inp = str(fail.get('input', ''))
            if len(inp) > (300 if not compact else 150):
                inp = inp[:(300 if not compact else 150)] + "...(truncated)"
            parts.append(f"  Input:\n{_indent(inp, 4)}")
            if fail.get('expected'):
                exp = str(fail.get('expected', ''))
                if len(exp) > (200 if not compact else 120):
                    exp = exp[:(200 if not compact else 120)] + "...(truncated)"
                parts.append(f"  Expected:\n{_indent(exp, 4)}")
            if fail.get('output'):
                out = str(fail.get('output', ''))
                if len(out) > (200 if not compact else 120):
                    out = out[:(200 if not compact else 120)] + "...(truncated)"
                parts.append(f"  Actual Output:\n{_indent(out, 4)}")
            if fail.get('details'):
                details = str(fail.get('details', ''))
                if len(details) > (200 if not compact else 120):
                    details = details[:(200 if not compact else 120)] + "...(truncated)"
                parts.append(f"  Details:\n{_indent(details, 4)}")
        failures_block = "\n".join(parts)

    fixes_block = ""
    if suggested_fixes:
        fixes_block = "Suggested Fixes:\n" + "\n".join([f"- {fix}" for fix in suggested_fixes])

    memory_block = f"\n{memory_advice}\n" if memory_advice else ""

    templates = load_prompt_templates()
    tpl = get_nested_template(templates, "generate_code.patch")
    if not isinstance(tpl, str):
        raise KeyError("generate_code.patch must be a string template")

    steps_block = "\n".join(steps)
    return render_placeholders(
        tpl,
        {
            "PROBLEM_DESC": problem_desc,
            "ABSTRACT_TAGS_LEVEL2_BLOCK": abstract_tags_level2_block,
            "ALGORITHM": algorithm,
            "STEPS": steps_block,
            "PREV_CODE": prev_code,
            "FAILURES_BLOCK": failures_block,
            "FEEDBACK_TEXT": feedback_text,
            "AGGREGATE_FAILURES_BLOCK": aggregate_failures_text,
            "FIXES_BLOCK": fixes_block,
            "MEMORY_ADVICE": memory_block,
        },
    )


def _build_regenerate_prompt(
    prev_code: str,
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    specific_failures: List[Dict],
    suggested_fixes: List[str],
    feedback_text: str,
    constraints: Dict[str, Any],
    public_tests: List[Dict],
    generated_tests: List[Dict],
    memory_advice: str = "",
    compact: bool = False,
    abstract_tags_level2_block: str = "",
) -> str:
    """Build prompt for full regeneration (no SEARCH/REPLACE format)."""
    prev_code = truncate_for_prompt(prev_code, 16000 if not compact else 8000, "PREV_CODE")
    problem_desc = truncate_for_prompt(problem_desc, 10000 if not compact else 5000, "PROBLEM_DESC")
    feedback_text = truncate_for_prompt(feedback_text, 5000 if not compact else 2200, "FEEDBACK_TEXT")
    constraints_block = ""
    if constraints:
        constraints_block = f"Constraints:\n  {compact_json_for_prompt(constraints, 2500 if not compact else 1200, 'CONSTRAINTS')}"

    public_block = ""
    if public_tests:
        parts = []
        for i, t in enumerate(public_tests[:3]):
            sample_input = truncate_for_prompt(t.get("input", ""), 400 if not compact else 180, f"PUBLIC_INPUT_{i+1}")
            sample_output = truncate_for_prompt(t.get("output", ""), 400 if not compact else 180, f"PUBLIC_OUTPUT_{i+1}")
            parts.append(f"  Sample {i+1}:")
            parts.append(f"    Input:\n{_indent(sample_input, 6)}")
            parts.append(f"    Output:\n{_indent(sample_output, 6)}")
        public_block = "Public test cases:\n" + "\n".join(parts)

    gen_block = ""
    if generated_tests:
        samples = generated_tests[:3]
        parts = []
        for i, t in enumerate(samples):
            inp = t.get("input", "").strip()
            if len(inp) > (300 if not compact else 150):
                inp = inp[: (300 if not compact else 150)] + "...(truncated)"
            parts.append(f"  Generated input {i+1}:\n{_indent(inp, 4)}")
        gen_block = "Sample generated inputs (for format/scale reference):\n" + "\n".join(parts)

    failures_block = ""
    if specific_failures:
        parts = ["The following test cases are FAILING:"]
        for i, fail in enumerate(specific_failures[:10]):
            parts.append(f"\nFailure {i+1} ({fail.get('type', 'Unknown Error')}):")
            inp = str(fail.get("input", ""))
            if len(inp) > (300 if not compact else 150):
                inp = inp[: (300 if not compact else 150)] + "...(truncated)"
            parts.append(f"  Input:\n{_indent(inp, 4)}")
            if fail.get("expected"):
                exp = str(fail.get("expected", ""))
                if len(exp) > (220 if not compact else 120):
                    exp = exp[: (220 if not compact else 120)] + "...(truncated)"
                parts.append(f"  Expected:\n{_indent(exp, 4)}")
            if fail.get("output"):
                out = str(fail.get("output", ""))
                if len(out) > (220 if not compact else 120):
                    out = out[: (220 if not compact else 120)] + "...(truncated)"
                parts.append(f"  Actual Output:\n{_indent(out, 4)}")
        failures_block = "\n".join(parts)

    fixes_block = ""
    if suggested_fixes:
        fixes_block = "Suggested Fixes:\n" + "\n".join([f"- {fix}" for fix in suggested_fixes])

    memory_block = f"\n{memory_advice}\n" if memory_advice else ""
    templates = load_prompt_templates()
    tpl = get_nested_template(templates, "generate_code.regenerate")
    if not isinstance(tpl, str):
        raise KeyError("generate_code.regenerate must be a string template")
    steps_block = "\n".join(steps)
    return render_placeholders(
        tpl,
        {
            "PROBLEM_DESC": problem_desc,
            "ABSTRACT_TAGS_LEVEL2_BLOCK": abstract_tags_level2_block,
            "ALGORITHM": algorithm,
            "STEPS": steps_block,
            "PREV_CODE": prev_code,
            "CONSTRAINTS_BLOCK": constraints_block,
            "PUBLIC_BLOCK": public_block,
            "GEN_BLOCK": gen_block,
            "FAILURES_BLOCK": failures_block,
            "FEEDBACK_TEXT": feedback_text,
            "FIXES_BLOCK": fixes_block,
            "MEMORY_ADVICE": memory_block,
        },
    )


def _format_aggregate_failures_text(aggregate_summary: Dict[str, Any]) -> str:
    """Format aggregate failure statistics for patch prompting."""
    if not aggregate_summary or not aggregate_summary.get("total_failed"):
        return ""

    lines = [
        "Aggregate failure summary across internal tests:",
        f"- Total failed tests: {aggregate_summary.get('total_failed', 0)}",
    ]

    judge_status_counts = aggregate_summary.get("judge_status_counts") or aggregate_summary.get("error_type_counts") or {}
    if judge_status_counts:
        lines.append("- Judge status counts:")
        for key, value in sorted(judge_status_counts.items()):
            lines.append(f"  - {key}: {value}")

    repair_subtype_counts = aggregate_summary.get("repair_subtype_counts") or {}
    if repair_subtype_counts:
        lines.append("- Repair subtype counts:")
        for key, value in sorted(repair_subtype_counts.items()):
            lines.append(f"  - {key}: {value}")

    input_length = aggregate_summary.get("input_length") or {}
    if input_length:
        lines.append(
            "- Failed input length stats: "
            f"min={input_length.get('min', 0)}, "
            f"avg={input_length.get('avg', 0)}, "
            f"max={input_length.get('max', 0)}"
        )

    numeric_diff = aggregate_summary.get("numeric_diff") or {}
    if numeric_diff:
        lines.append(
            "- Numeric diff summary: "
            f"count={numeric_diff.get('count', 0)}, "
            f"avg={numeric_diff.get('avg_diff', 0):.4g}, "
            f"min={numeric_diff.get('min_diff', 0):.4g}, "
            f"max={numeric_diff.get('max_diff', 0):.4g}"
        )

    representative_examples = aggregate_summary.get("representative_examples") or {}
    if representative_examples:
        lines.append("- Representative grouped examples:")
        for failure_type, examples in sorted(representative_examples.items()):
            lines.append(f"  {failure_type}:")
            for idx, example in enumerate(examples[:2], start=1):
                lines.append(f"    Example {idx} input: {example.get('input', '')}")
                if example.get("expected"):
                    lines.append(f"    Expected: {example.get('expected', '')}")
                if example.get("actual"):
                    lines.append(f"    Actual: {example.get('actual', '')}")
                if example.get("error"):
                    lines.append(f"    Error: {example.get('error', '')}")
                if example.get("repair_subtype"):
                    lines.append(f"    Repair subtype: {example.get('repair_subtype', '')}")

    return "\n".join(lines)

def _build_repair_decision_prompt(
    prev_code: str,
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    specific_failures: List[Dict],
    suggested_fixes: List[str],
    feedback_text: str,
    aggregate_failures_text: str = "",
    diagnostic_text: str = "",
    memory_advice: str = "",
    compact: bool = False,
    abstract_tags_level2_block: str = "",
) -> str:
    prev_code = truncate_for_prompt(prev_code, 16000 if not compact else 8000, "PREV_CODE")
    problem_desc = truncate_for_prompt(problem_desc, 9000 if not compact else 4500, "PROBLEM_DESC")
    feedback_text = truncate_for_prompt(feedback_text, 5000 if not compact else 2000, "FEEDBACK_TEXT")
    aggregate_failures_text = truncate_for_prompt(
        aggregate_failures_text,
        4000 if not compact else 1600,
        "AGGREGATE_FAILURES_TEXT",
    )
    diagnostic_text = truncate_for_prompt(diagnostic_text, 4000 if not compact else 1600, "DIAGNOSTIC_TEXT")

    failures_block = ""
    if specific_failures:
        parts = ["Representative failures:"]
        for i, fail in enumerate(specific_failures[:10]):
            parts.append(f"\nFailure {i+1} ({fail.get('type', 'Unknown Error')}):")
            inp = truncate_for_prompt(str(fail.get("input", "")), 300 if not compact else 150, f"FAIL_INPUT_{i+1}")
            parts.append(f"  Input:\n{_indent(inp, 4)}")
            if fail.get("expected"):
                exp = truncate_for_prompt(str(fail.get("expected", "")), 220 if not compact else 120, f"FAIL_EXPECTED_{i+1}")
                parts.append(f"  Expected:\n{_indent(exp, 4)}")
            if fail.get("output"):
                out = truncate_for_prompt(str(fail.get("output", "")), 220 if not compact else 120, f"FAIL_OUTPUT_{i+1}")
                parts.append(f"  Actual Output:\n{_indent(out, 4)}")
            if fail.get("details"):
                details = truncate_for_prompt(str(fail.get("details", "")), 220 if not compact else 120, f"FAIL_DETAILS_{i+1}")
                parts.append(f"  Details:\n{_indent(details, 4)}")
        failures_block = "\n".join(parts)

    fixes_block = ""
    if suggested_fixes:
        fixes_block = "Suggested Fixes:\n" + "\n".join([f"- {fix}" for fix in suggested_fixes])

    diagnostic_block = diagnostic_text.strip()
    if diagnostic_block:
        diagnostic_block = "## Diagnostic Evidence\n" + diagnostic_block

    memory_block = f"\n{memory_advice}\n" if memory_advice else ""
    templates = load_prompt_templates()
    tpl = get_nested_template(templates, "generate_code.patch_decision")
    if not isinstance(tpl, str):
        raise KeyError("generate_code.patch_decision must be a string template")

    steps_block = "\n".join(steps)
    return render_placeholders(
        tpl,
        {
            "PROBLEM_DESC": problem_desc,
            "ABSTRACT_TAGS_LEVEL2_BLOCK": abstract_tags_level2_block,
            "ALGORITHM": algorithm,
            "STEPS": steps_block,
            "PREV_CODE": prev_code,
            "FAILURES_BLOCK": failures_block,
            "AGGREGATE_FAILURES_BLOCK": aggregate_failures_text,
            "DIAGNOSTIC_BLOCK": diagnostic_block,
            "FEEDBACK_TEXT": feedback_text,
            "FIXES_BLOCK": fixes_block,
            "MEMORY_ADVICE": memory_block,
        },
    )


def _parse_repair_mode_decision(raw: str) -> Dict[str, str]:
    fallback = {"mode": "patch", "confidence": "low", "reason": "fallback-to-patch"}
    try:
        parsed = parse_json_response(raw)
    except Exception:
        return fallback
    mode = str(parsed.get("mode", "patch") or "patch").strip().lower()
    confidence = str(parsed.get("confidence", "low") or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    reason = str(parsed.get("reason", "") or "").strip() or fallback["reason"]
    if mode not in {"patch", "full_regen"}:
        mode = "patch"
    return {"mode": mode, "confidence": confidence, "reason": reason}


def _choose_repair_mode(
    llm: UnifiedLLMClient,
    prev_code: str,
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    specific_failures: List[Dict],
    suggested_fixes: List[str],
    feedback_text: str,
    aggregate_failures_text: str,
    diagnostic_text: str,
    memory_advice: str,
    abstract_tags_level2_block: str,
    *,
    messages_history: Optional[list],
    compaction_context: Optional[Dict[str, Any]],
    compaction_config: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, str], List[Dict[str, str]], List[Dict[str, str]]]:
    response, new_messages, persisted_messages = _call_generate_with_history(
        llm,
        _build_repair_decision_prompt,
        prev_code,
        problem_desc,
        algorithm,
        steps,
        specific_failures,
        suggested_fixes,
        feedback_text,
        aggregate_failures_text,
        diagnostic_text,
        memory_advice=memory_advice,
        abstract_tags_level2_block=abstract_tags_level2_block,
        messages_history=messages_history,
        _stage="generate_code.patch_decision",
        _compaction_context=compaction_context,
        _compaction_config=compaction_config,
    )
    return _parse_repair_mode_decision(response), new_messages, persisted_messages


def _log_prompt(stage: str, prompt: str, compact: bool) -> None:
    logger.debug(f"[PROMPT_BODY:{stage}] compact={int(compact)}\n{prompt}")


def _generate_with_compact_retry(
    llm: UnifiedLLMClient,
    prompt_builder,
    *args,
    _messages_history: Optional[list] = None,
    _stage: str = "generate_code",
    _compaction_context: Optional[Dict[str, Any]] = None,
    _compaction_config: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> tuple | str:
    """Build prompt, call LLM, and optionally thread conversation history."""
    history = _messages_history if _messages_history is not None else []
    prompt = prompt_builder(*args, compact=False, **kwargs)
    _log_prompt(_stage, prompt, compact=False)
    try:
        if _messages_history is None:
            return llm.generate(prompt)
        return chat_with_history(
            llm,
            history,
            prompt,
            compaction_context=_compaction_context,
            compaction_config=_compaction_config,
        )
    except PromptTooLongError:
        compact_prompt = prompt_builder(*args, compact=True, **kwargs)
        _log_prompt(_stage, compact_prompt, compact=True)
        logger.warning("[GenCode] Prompt exceeded max tokens, retrying with compact prompt")
        if _messages_history is None:
            return llm.generate(compact_prompt)
        return chat_with_history(
            llm,
            history,
            compact_prompt,
            compaction_context=_compaction_context,
            compaction_config=_compaction_config,
        )


def _call_generate_with_history(
    llm: UnifiedLLMClient,
    prompt_builder,
    *args,
    messages_history: Optional[list] = None,
    _stage: str = "generate_code",
    _compaction_context: Optional[Dict[str, Any]] = None,
    _compaction_config: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
    result = _generate_with_compact_retry(
        llm,
        prompt_builder,
        *args,
        _messages_history=messages_history,
        _stage=_stage,
        _compaction_context=_compaction_context,
        _compaction_config=_compaction_config,
        **kwargs,
    )
    if messages_history is None:
        return str(result), [], []
    return normalize_chat_history_result(result)


def _indent(text: str, n: int) -> str:
    prefix = " " * n
    return "\n".join(prefix + line for line in text.strip().splitlines())


def _build_verification_set(
    public_tests: List[Dict],
    generated_tests: List[Dict],
    max_generated_tests: int = 5,
) -> List[Dict]:
    """Build the verification set: public tests + configurable generated tests with expected_output."""
    verify = []
    for i, t in enumerate(public_tests):
        verify.append({
            "id": f"public_{i}",
            "input": t.get("input", ""),
            "expected_output": t.get("output", ""),
        })

    count = 0
    for i, t in enumerate(generated_tests):
        if count >= max_generated_tests:
            break
        eo = t.get("expected_output", "")
        if eo:
            verify.append({
                "id": f"generated_{i}",
                "input": t.get("input", ""),
                "expected_output": eo,
            })
            count += 1

    return verify


def _self_validate(
    code: str, verify_set: List[Dict], checker_exe: Optional[Path] = None
) -> Tuple[bool, List[Dict], int]:
    """Compile and run code against verify_set.

    Returns (all_passed, failures, total_run).
    Early-terminates after 3 consecutive failures to avoid wasting time.
    """
    if not verify_set:
        return True, [], 0

    tmp = Path(tempfile.mkdtemp())
    try:
        src_path = tmp / "solution.cpp"
        exe_path = tmp / "solution.exe"
        src_path.write_text(code, encoding="utf-8")

        ok, compile_log = compile_cpp(src_path, exe_path, limits=ExecutionLimits.default_compile())
        if not ok:
            return False, [{"type": "compile_error", "message": compile_log}], 0

        failures = []
        consecutive_fails = 0
        total_run = 0

        for i, tc in enumerate(verify_set):
            inp = tc["input"]
            expected = tc["expected_output"].strip()
            total_run += 1
            try:
                retcode, stdout, stderr = run_program(exe_path, input_text=inp, limits=ExecutionLimits.default_run())
            except Exception as e:
                failures.append({
                    "id": tc["id"],
                    "type": "runtime_error",
                    "input": inp[:200],
                    "message": str(e),
                })
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    break
                continue

            if retcode != 0:
                failures.append({
                    "id": tc["id"],
                    "type": "runtime_error",
                    "input": inp[:200],
                    "message": stderr[:300] if stderr else "non-zero exit",
                })
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    break
                continue

            actual = stdout.strip()
            passed_test = False
            error_msg = None

            input_file = tmp / f"input_{i}.txt"
            output_file = tmp / f"output_{i}.txt"
            answer_file = tmp / f"answer_{i}.txt"

            input_file.write_text(inp, encoding="utf-8")
            output_file.write_text(stdout, encoding="utf-8")
            answer_file.write_text(expected, encoding="utf-8")

            passed_test, error_msg = judge_output_against_certified_expected(
                actual_output=stdout,
                expected_output=expected,
                checker_exe=checker_exe,
                input_path=input_file,
                output_path=output_file,
                answer_path=answer_file,
            )

            if not passed_test:
                failures.append({
                    "id": tc["id"],
                    "type": "wrong_answer",
                    "input": inp[:200],
                    "expected": expected[:200],
                    "actual": actual[:200],
                    "message": error_msg,
                })
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    break
            else:
                consecutive_fails = 0
        return len(failures) == 0, failures, total_run
    finally:
        cleanup_tempdir(tmp, windows_ignore_permission_errors=True)



def _format_self_validation_feedback(failures: List[Dict], total_run: int, total_verify: int) -> str:
    """Format self-validation failures into prompt feedback.

    Picks up to 3 representative failures (one per error type) to keep prompt concise.
    """
    header = render_template(
        "generate_code.self_validation_header",
        FAIL_COUNT=str(len(failures)),
        TOTAL_RUN=str(total_run),
        TOTAL_VERIFY=str(total_verify),
    ).rstrip()

    compile_errors = [f for f in failures if f.get("type") == "compile_error"]
    runtime_errors = [f for f in failures if f.get("type") == "runtime_error"]
    wrong_answers = [f for f in failures if f.get("type") == "wrong_answer"]

    picked = []
    if compile_errors:
        picked.append(compile_errors[0])
    if runtime_errors:
        picked.append(runtime_errors[0])
    if wrong_answers:
        picked.extend(wrong_answers[:2])

    detail_lines: List[str] = []
    for f in picked[:3]:
        if f.get("type") == "compile_error":
            detail_lines.append(f"  Compilation error:\n    {f.get('message', '?')[:500]}")
        elif f.get("type") == "runtime_error":
            detail_lines.append(f"  Runtime error on test {f.get('id', '?')}:")
            detail_lines.append(f"    Error: {f.get('message', '?')}")
        elif f.get("type") == "wrong_answer":
            detail_lines.append(f"  Wrong answer on test {f.get('id', '?')}:")
            inp = f.get('input', '?')[:100]
            expected = f.get('expected', '?')[:100]
            actual = f.get('actual', '?')[:100]
            detail_lines.append(f"    Input:    {inp}")
            detail_lines.append(f"    Expected: {expected}")
            detail_lines.append(f"    Actual:   {actual}")

    footer = "\n" + render_template("generate_code.self_validation_footer").strip()
    return header + "\n\n" + "\n".join(detail_lines) + footer


def generate_code_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Generate C++ solution code using LLM.
    
    - First iteration: Generate complete code
    - Subsequent iterations: Use SEARCH/REPLACE patches to fix bugs
    
    All changes use the patch-based approach for traceability.
    """
    logger.info(f"[Node] Generating C++ code (version {state['solution'].get('version', 0) + 1})")

    if state.get("skip_generate_code", False):
        logger.info("[GenCode] Skipping generation: feedback not ready or unchanged")
        return {
            "execution_log": ["Code generation skipped: feedback not ready or unchanged"],
            "llm_calls": 0,
            "skip_generate_code": False,
        }

    # Use 'code' role for better code generation quality
    code_config = UnifiedLLMClient.build_role_config(state["config"], "code")
    llm = UnifiedLLMClient(code_config)
    llm_calls = 0

    # Prefer canonical problem representation if available
    canonical = state["problem"].get("canonical", {})
    if canonical:
        problem_desc = render_template(
            "generate_code.canonical_problem_block",
            OBJECTIVE=str(canonical.get("objective", "")),
            INPUTS_JSON=json.dumps(canonical.get("inputs", {}), indent=2),
            OUTPUTS_JSON=json.dumps(canonical.get("outputs", {}), indent=2),
            CONSTRAINTS_JSON=json.dumps(canonical.get("constraints", {}), indent=2),
            REQUIRED_PROPERTIES=str(canonical.get("required_properties", [])),
        )
    else:
        problem_desc = state["problem"].get("description", "")

    algorithm = state["plan"].get("algorithm_choice", "")
    steps = state["plan"].get("implementation_steps", [])
    constraints = state["problem"].get("constraints", {})
    public_tests = state["problem"].get("public_tests", [])
    generated_tests = state.get("tests", {}).get("generated_tests", [])
    max_verification_generated_tests = int(
        (state.get("config", {}) or {}).get("generate_code_verification_generated_tests", 5)
    )
    iteration = state.get("iteration", 0)

    raw_l2 = state["problem"].get("tags_level2_selected") or []
    tags_l2_list = [str(x) for x in raw_l2] if isinstance(raw_l2, list) else []
    abstract_tags_level2_block = _format_abstract_tags_level2_block(tags_l2_list)

    # Initialize solve memory
    memory = MemoryClient(
        namespace=MemoryNamespace.SOLVE,
        config=state["config"],
        problem_desc=problem_desc,
        canonical=canonical,
    )
    
    # Get memory injection
    failure_type = None
    if iteration > 0:
        feedback_data = state.get("feedback", {}).get("feedback", {})
        error_pattern = feedback_data.get("error_pattern", "")
        if "compile" in error_pattern.lower():
            failure_type = "COMPILE_FAIL"
        elif "timeout" in error_pattern.lower() or "tle" in error_pattern.lower():
            failure_type = "TIMEOUT"
        else:
            failure_type = "SOLVE_WA"
    
    memory_advice, memory_item_ids = memory.get_injection(
        fsm_state="SOLVE_DRAFT",
        failure_type=failure_type,
        attempt_count=iteration,
    )

    # Build verification set
    verify_set = _build_verification_set(
        public_tests,
        generated_tests,
        max_generated_tests=max_verification_generated_tests,
    )
    checker_exe_str = state.get("tests", {}).get("checker_exe")
    checker_exe = Path(checker_exe_str) if checker_exe_str else None

    max_self_attempts = 3
    code = ""
    self_validation_log = []
    prev_code = state["solution"].get("code", "")
    all_new_messages: List[Dict[str, str]] = []
    history = list(state.get("messages", []))
    compaction_context = build_chat_compaction_context(state, node_name="generate_code")
    compaction_config = state.get("config")

    # Determine if this is initial generation or patch iteration
    is_initial = (iteration == 0 or not prev_code)

    solver_graph_block = ""
    solver_state_update: Dict[str, Any] = {}
    if is_initial:
        sn = state["config"].get("solver_network") or {}
        if sn.get("enabled") and not state.get("solver_network_oneshot_spent"):
            solver_graph_block = build_solver_network_block(state, state["config"])
            solver_state_update["solver_network_oneshot_spent"] = True
    
    mode_label = "initial"
    if is_initial:
        # First time: generate complete code
        logger.info("[GenCode] Initial generation (no previous code)")
        
        initial_self_validation_feedback = ""
        for attempt in range(1, max_self_attempts + 1):
            response, new_msgs, persisted_messages = _call_generate_with_history(
                llm,
                _build_initial_prompt,
                problem_desc, algorithm, steps,
                constraints, public_tests, generated_tests,
                memory_advice=memory_advice,
                solver_graph_block=solver_graph_block,
                abstract_tags_level2_block=abstract_tags_level2_block,
                self_validation_feedback=initial_self_validation_feedback,
                messages_history=history,
                _stage="generate_code.initial",
                _compaction_context=compaction_context,
                _compaction_config=compaction_config,
            )
            llm_calls += 1
            all_new_messages.extend(new_msgs)
            history = list(persisted_messages)
            code = sanitize_cpp(response)

            # Self-validate
            passed, failures, total_run = _self_validate(code, verify_set, checker_exe)

            if passed:
                self_validation_log.append(
                    f"Self-validation attempt {attempt}: PASSED all {len(verify_set)} cases"
                )
                logger.info(f"[GenCode] Self-validation passed on attempt {attempt}")
                break

            fail_summary = f"Self-validation attempt {attempt}: FAILED ({len(failures)} issue(s) in {total_run}/{len(verify_set)} cases)"
            self_validation_log.append(fail_summary)
            logger.info(f"[GenCode] {fail_summary}")

            if attempt < max_self_attempts:
                initial_self_validation_feedback = _format_self_validation_feedback(
                    failures,
                    total_run,
                    len(verify_set),
                )
    
    else:
        # Extract feedback from previous iteration
        feedback_text = ""
        specific_failures = []
        suggested_fixes = []
        aggregate_failures_text = ""
        diagnostic_text = ""
        code = prev_code

        if iteration > 0:
            feedback_data = state.get("feedback", {}).get("feedback", {})
            specific_failures = feedback_data.get("failures", [])
            aggregate_summary = feedback_data.get("aggregate_summary", {})
            aggregate_failures_text = _format_aggregate_failures_text(aggregate_summary)
            suggested_fixes = state.get("feedback", {}).get("suggested_fixes", [])

            analysis = feedback_data.get("analysis", "")
            error_pattern = feedback_data.get("error_pattern", "")
            if analysis:
                feedback_text = f"Analysis: {analysis}\nError Pattern: {error_pattern}"

        for attempt in range(1, max_self_attempts + 1):
            decision, decision_msgs, decision_persisted = _choose_repair_mode(
                llm,
                code,
                problem_desc,
                algorithm,
                steps,
                specific_failures,
                suggested_fixes,
                feedback_text,
                aggregate_failures_text,
                diagnostic_text,
                memory_advice,
                abstract_tags_level2_block,
                messages_history=history,
                compaction_context=compaction_context,
                compaction_config=compaction_config,
            )
            llm_calls += 1
            all_new_messages.extend(decision_msgs)
            history = list(decision_persisted)
            revision_mode = decision["mode"]
            mode_label = revision_mode
            self_validation_log.append(
                f"Decision attempt {attempt}: {revision_mode} ({decision['confidence']}) - {decision['reason']}"
            )

            if revision_mode == "patch":
                llm_response, new_msgs, persisted_messages = _call_generate_with_history(
                    llm,
                    _build_patch_prompt,
                    code,
                    problem_desc,
                    algorithm,
                    steps,
                    specific_failures,
                    suggested_fixes,
                    feedback_text,
                    aggregate_failures_text,
                    memory_advice=memory_advice,
                    abstract_tags_level2_block=abstract_tags_level2_block,
                    messages_history=history,
                    _stage="generate_code.patch",
                    _compaction_context=compaction_context,
                    _compaction_config=compaction_config,
                )
                llm_calls += 1
                all_new_messages.extend(new_msgs)
                history = list(persisted_messages)

                blocks = parse_search_replace_blocks(llm_response)
                if not blocks:
                    logger.warning(f"[GenCode] No SEARCH/REPLACE blocks found in LLM response (attempt {attempt})")
                    self_validation_log.append(f"Patch attempt {attempt}: No valid SEARCH/REPLACE blocks found")
                    continue

                success, patched_code, error_msg = apply_search_replace_blocks(code, blocks)
                if not success:
                    logger.warning(f"[GenCode] Patch application failed: {error_msg} (attempt {attempt})")
                    self_validation_log.append(f"Patch attempt {attempt}: Failed to apply - {error_msg}")
                    continue

                diff = compute_unified_diff(code, patched_code)
                logger.debug(f"[GenCode] Patch diff:\n{diff}")
                code = patched_code
            else:
                response, new_msgs, persisted_messages = _call_generate_with_history(
                    llm,
                    _build_regenerate_prompt,
                    code,
                    problem_desc,
                    algorithm,
                    steps,
                    specific_failures,
                    suggested_fixes,
                    feedback_text,
                    constraints,
                    public_tests,
                    generated_tests,
                    memory_advice=memory_advice,
                    abstract_tags_level2_block=abstract_tags_level2_block,
                    messages_history=history,
                    _stage="generate_code.regenerate",
                    _compaction_context=compaction_context,
                    _compaction_config=compaction_config,
                )
                llm_calls += 1
                all_new_messages.extend(new_msgs)
                history = list(persisted_messages)
                code = sanitize_cpp(response)

            passed, failures, total_run = _self_validate(code, verify_set, checker_exe)

            if passed:
                if revision_mode == "patch":
                    self_validation_log.append(
                        f"Patch attempt {attempt}: PASSED all {len(verify_set)} cases"
                    )
                    logger.info(f"[GenCode] Patch validation passed on attempt {attempt}")
                else:
                    self_validation_log.append(
                        f"Regenerate attempt {attempt}: PASSED all {len(verify_set)} cases"
                    )
                    logger.info(f"[GenCode] Regenerate validation passed on attempt {attempt}")
                break

            if revision_mode == "patch":
                fail_summary = (
                    f"Patch attempt {attempt}: FAILED ({len(failures)} issue(s) in "
                    f"{total_run}/{len(verify_set)} cases)"
                )
            else:
                fail_summary = (
                    f"Regenerate attempt {attempt}: FAILED ({len(failures)} issue(s) in "
                    f"{total_run}/{len(verify_set)} cases)"
                )
            self_validation_log.append(fail_summary)
            logger.info(f"[GenCode] {fail_summary}")

            if attempt < max_self_attempts:
                feedback_text = _format_self_validation_feedback(failures, total_run, len(verify_set))
                aggregate_failures_text = ""
                specific_failures = [
                    {
                        "type": f.get("type", "unknown"),
                        "input": f.get("input", ""),
                        "expected": f.get("expected", ""),
                        "output": f.get("actual", ""),
                        "details": f.get("message", ""),
                    }
                    for f in failures
                ]

    # Build solution dict
    version = state["solution"].get("version", 0) + 1
    problem_code = extract_problem_code(state.get("raw_problem", {}))
    if problem_code:
        out_dir = Path("data") / "generated" / problem_code / "code"
        sn = (state.get("config") or {}).get("solver_network") or {}
        ens_b = sn.get("ensemble_branch_id")
        if ens_b is not None:
            out_dir = out_dir / f"ensemble_b{int(ens_b)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"solution_v{version}.cpp").write_text(code, encoding="utf-8")
        (out_dir / "solution_latest.cpp").write_text(code, encoding="utf-8")

    solution = {
        "code": code,
        "version": version,
        "compilation_success": False,
        "compilation_errors": [],
        "executable_path": None,
        "memory_item_ids": memory_item_ids,
    }

    out: Dict[str, Any] = {
        "solution": solution,
        "messages": all_new_messages,
        "execution_log": [
            f"Generated C++ code (v{solution['version']}), {llm_calls} LLM call(s)",
            f"  Mode: {mode_label}",
            f"  Solve memory items injected: {len(memory_item_ids)}",
            *self_validation_log,
        ],
        "llm_calls": llm_calls,
    }
    if solver_state_update:
        out.update(solver_state_update)
    return out
