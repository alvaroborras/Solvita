"""Generate Code Node - Generate C++ solution code with lightweight self-validation"""

import json
import tempfile
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from loguru import logger
from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.utils.cpp_execution import (
    sanitize_cpp,
    compile_cpp,
    run_program,
    ExecutionLimits,
    cleanup_tempdir,
)
from src.utils.output_judging import judge_output_against_certified_expected
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
    memory_advice: str = "",
    compact: bool = False,
    abstract_tags_level2_block: str = "",
) -> str:
    """Build prompt for patching existing code using SEARCH/REPLACE."""
    prev_code = truncate_for_prompt(prev_code, 16000 if not compact else 8000, "PREV_CODE")
    problem_desc = truncate_for_prompt(problem_desc, 9000 if not compact else 4500, "PROBLEM_DESC")
    feedback_text = truncate_for_prompt(feedback_text, 5000 if not compact else 2000, "FEEDBACK_TEXT")

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


def _generate_with_compact_retry(
    llm: UnifiedLLMClient,
    prompt_builder,
    *args,
    **kwargs,
) -> str:
    prompt = prompt_builder(*args, compact=False, **kwargs)
    try:
        return llm.generate(prompt)
    except PromptTooLongError:
        compact_prompt = prompt_builder(*args, compact=True, **kwargs)
        logger.warning("[GenCode] Prompt exceeded max tokens, retrying with compact prompt")
        return llm.generate(compact_prompt)


def _indent(text: str, n: int) -> str:
    prefix = " " * n
    return "\n".join(prefix + line for line in text.strip().splitlines())


def _build_verification_set(
    public_tests: List[Dict], generated_tests: List[Dict]
) -> List[Dict]:
    """Build the verification set: public tests + up to 5 generated tests with expected_output."""
    verify = []
    for i, t in enumerate(public_tests):
        verify.append({
            "id": f"public_{i}",
            "input": t.get("input", ""),
            "expected_output": t.get("output", ""),
        })

    # Add up to 5 generated tests with expected_output
    count = 0
    for i, t in enumerate(generated_tests):
        if count >= 5:
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
    verify_set = _build_verification_set(public_tests, generated_tests)
    checker_exe_str = state.get("tests", {}).get("checker_exe")
    checker_exe = Path(checker_exe_str) if checker_exe_str else None

    max_self_attempts = 3
    code = ""
    self_validation_log = []
    prev_code = state["solution"].get("code", "")
    
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
        
        for attempt in range(1, max_self_attempts + 1):
            code = _generate_with_compact_retry(
                llm,
                _build_initial_prompt,
                problem_desc, algorithm, steps,
                constraints, public_tests, generated_tests,
                memory_advice=memory_advice,
                solver_graph_block=solver_graph_block,
                abstract_tags_level2_block=abstract_tags_level2_block,
            )
            llm_calls += 1
            code = sanitize_cpp(code)

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
                # For next attempt within initial generation, still regenerate complete code
                # but inject failure info
                pass
    
    else:
        revision_mode = str(((state.get("config") or {}).get("codegen", {}) or {}).get("revision_mode", "patch")).strip().lower()
        if revision_mode not in {"patch", "full_regen"}:
            revision_mode = "patch"
        mode_label = revision_mode
        if revision_mode == "patch":
            # Patch mode: use SEARCH/REPLACE to fix previous code
            logger.info("[GenCode] Patch mode (fixing previous code)")
        else:
            # Regeneration mode: rewrite full code on repair iterations
            logger.info("[GenCode] Full regeneration mode (rewriting entire code)")
        
        # Extract feedback from previous iteration
        feedback_text = ""
        specific_failures = []
        suggested_fixes = []
        
        if iteration > 0:
            feedback_data = state.get("feedback", {}).get("feedback", {})
            specific_failures = feedback_data.get("failures", [])
            suggested_fixes = state.get("feedback", {}).get("suggested_fixes", [])
            
            analysis = feedback_data.get("analysis", "")
            error_pattern = feedback_data.get("error_pattern", "")
            if analysis:
                feedback_text = f"Analysis: {analysis}\nError Pattern: {error_pattern}"
        
        for attempt in range(1, max_self_attempts + 1):
            if revision_mode == "patch":
                llm_response = _generate_with_compact_retry(
                    llm,
                    _build_patch_prompt,
                    prev_code,
                    problem_desc,
                    algorithm,
                    steps,
                    specific_failures,
                    suggested_fixes,
                    feedback_text,
                    memory_advice=memory_advice,
                    abstract_tags_level2_block=abstract_tags_level2_block,
                )
                llm_calls += 1

                # Parse SEARCH/REPLACE blocks
                blocks = parse_search_replace_blocks(llm_response)

                if not blocks:
                    logger.warning(f"[GenCode] No SEARCH/REPLACE blocks found in LLM response (attempt {attempt})")
                    self_validation_log.append(f"Patch attempt {attempt}: No valid SEARCH/REPLACE blocks found")
                    code = prev_code  # Keep previous code
                    continue

                # Apply patches
                success, patched_code, error_msg = apply_search_replace_blocks(prev_code, blocks)

                if not success:
                    logger.warning(f"[GenCode] Patch application failed: {error_msg} (attempt {attempt})")
                    self_validation_log.append(f"Patch attempt {attempt}: Failed to apply - {error_msg}")
                    code = prev_code  # Keep previous code
                    continue

                # Log the diff for traceability
                diff = compute_unified_diff(prev_code, patched_code)
                logger.debug(f"[GenCode] Patch diff:\n{diff}")
                code = patched_code
            else:
                code = _generate_with_compact_retry(
                    llm,
                    _build_regenerate_prompt,
                    prev_code,
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
                )
                llm_calls += 1
                code = sanitize_cpp(code)

            # Self-validate repaired code
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
                # For next repair attempt, inject validation failures
                feedback_text = _format_self_validation_feedback(failures, total_run, len(verify_set))
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
