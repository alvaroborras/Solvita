"""Generate Code Node - Generate C++ solution code with lightweight self-validation"""

import json
import tempfile
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from loguru import logger
from src.llm import UnifiedLLMClient
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


def _build_initial_prompt(
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    constraints: Dict[str, Any],
    public_tests: List[Dict],
    generated_tests: List[Dict],
    memory_advice: str = "",
    compact: bool = False,
) -> str:
    """Build prompt for initial code generation (no previous code)."""
    desc_chars = 10000 if not compact else 5000
    constraint_chars = 2500 if not compact else 1200
    generated_chars = 300 if not compact else 150
    public_chars = 400 if not compact else 180
    problem_desc = truncate_for_prompt(problem_desc, desc_chars, "PROBLEM_DESC")
    
    # Format public tests
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

    # Format constraints
    constraints_block = ""
    if constraints:
        constraints_block = f"Constraints:\n  {compact_json_for_prompt(constraints, constraint_chars, 'CONSTRAINTS')}"

    # Format generated test inputs (first 3, input only)
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

    advice_section = f"\n{memory_advice}\n" if memory_advice else ""
    
    return f"""Generate a complete C++ solution for this competitive programming problem:

Problem: {problem_desc}

Algorithm to use: {algorithm}

Implementation steps:
{chr(10).join(steps)}

{constraints_block}

{public_block}

{gen_block}
{advice_section}

Requirements:
- Use standard C++ (C++17)
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Include all necessary headers
- Implement fast I/O
- Handle all edge cases
- Optimize for BOTH time and space complexity
- Before coding, do an internal resource audit using the stated constraints
- Every major container or table must have a size that is defensible under the maximum input bounds
- Avoid any implementation whose memory or time scales as the product of two large unconstrained dimensions unless you can prove it is safe
- Do not allocate dense matrices / DP tables / adjacency tables over max-sized dimensions by default
- If the provided algorithm sketch would lead to an unsafe implementation, adapt the implementation strategy instead of following the sketch literally
- Prefer streaming, aggregated counting, rolling-state, sparse, or compressed representations when full tables would be too large
- The final code must be realistic for competitive-programming limits, not just mathematically plausible

Generate ONLY the complete C++ code, no explanations."""


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
) -> str:
    """Build prompt for patching existing code using SEARCH/REPLACE."""
    prev_code = truncate_for_prompt(prev_code, 16000 if not compact else 8000, "PREV_CODE")
    problem_desc = truncate_for_prompt(problem_desc, 9000 if not compact else 4500, "PROBLEM_DESC")
    feedback_text = truncate_for_prompt(feedback_text, 5000 if not compact else 2000, "FEEDBACK_TEXT")
    
    # Format specific failures (up to 10)
    failures_block = ""
    if specific_failures:
        parts = ["The following test cases are FAILING:"]
        for i, fail in enumerate(specific_failures[:10]):
            parts.append(f"\nFailure {i+1} ({fail.get('type', 'Unknown Error')}):")
            # Truncate input if too long
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

    # Format suggested fixes
    fixes_block = ""
    if suggested_fixes:
        fixes_block = "Suggested Fixes:\n" + "\n".join([f"- {fix}" for fix in suggested_fixes])
    
    advice_section = f"\n{memory_advice}\n" if memory_advice else ""
    
    return f"""You are debugging a C++ solution that is FAILING tests. Your task is to generate SEARCH/REPLACE edits to fix the bugs.

Problem: {problem_desc}

Algorithm: {algorithm}

Implementation steps:
{chr(10).join(steps)}

## Current Code (BUGGY):
```cpp
{prev_code}
```

## Test Failures:
{failures_block}

{feedback_text}

{fixes_block}
{advice_section}

## Your Task:
Analyze the failures and generate *SEARCH/REPLACE* edits to fix the bugs.

Every *SEARCH/REPLACE* edit must use this EXACT format:
<<<<<<< SEARCH
<exact contiguous code snippet from the current code>
=======
<replacement code with the fix>
>>>>>>> REPLACE

**CRITICAL RULES:**
1. The SEARCH block must match the current code EXACTLY (including whitespace, indentation)
2. The SEARCH block must appear EXACTLY ONCE in the code
3. You can have multiple SEARCH/REPLACE blocks to fix multiple issues
4. Preserve proper indentation in the REPLACE block
5. Make minimal, surgical changes - only fix what's broken
6. Re-check BOTH time and space complexity before proposing edits
7. Replace unsafe data structures if the current implementation appears to allocate memory proportional to a dangerous product of input dimensions
8. Do not preserve an existing approach just because it matches the plan if it is not implementable within the stated limits

Example:
<<<<<<< SEARCH
    for (int i = 1; i <= n; i++) {{
        sum += arr[i];
    }}
=======
    for (int i = 0; i < n; i++) {{
        sum += arr[i];
    }}
>>>>>>> REPLACE

Generate the SEARCH/REPLACE edits now:"""


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
    lines = [f"Self-validation failed: {len(failures)} issues in {total_run}/{total_verify} cases tested:"]

    # Categorize failures
    compile_errors = [f for f in failures if f.get("type") == "compile_error"]
    runtime_errors = [f for f in failures if f.get("type") == "runtime_error"]
    wrong_answers = [f for f in failures if f.get("type") == "wrong_answer"]

    # Pick representative failures (up to 3 total)
    picked = []
    if compile_errors:
        picked.append(compile_errors[0])
    if runtime_errors:
        picked.append(runtime_errors[0])
    if wrong_answers:
        picked.extend(wrong_answers[:2])

    for f in picked[:3]:
        if f.get("type") == "compile_error":
            lines.append(f"  Compilation error:\n    {f.get('message', '?')[:500]}")
        elif f.get("type") == "runtime_error":
            lines.append(f"  Runtime error on test {f.get('id', '?')}:")
            lines.append(f"    Error: {f.get('message', '?')}")
        elif f.get("type") == "wrong_answer":
            lines.append(f"  Wrong answer on test {f.get('id', '?')}:")
            inp = f.get('input', '?')[:100]
            expected = f.get('expected', '?')[:100]
            actual = f.get('actual', '?')[:100]
            lines.append(f"    Input:    {inp}")
            lines.append(f"    Expected: {expected}")
            lines.append(f"    Actual:   {actual}")

    lines.append("Please fix these issues.")
    return "\n".join(lines)


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
        problem_desc = f"""Objective: {canonical.get('objective', '')}
Inputs: {json.dumps(canonical.get('inputs', {}), indent=2)}
Outputs: {json.dumps(canonical.get('outputs', {}), indent=2)}
Constraints: {json.dumps(canonical.get('constraints', {}), indent=2)}
Required Properties: {canonical.get('required_properties', [])}"""
    else:
        problem_desc = state["problem"].get("description", "")

    algorithm = state["plan"].get("algorithm_choice", "")
    steps = state["plan"].get("implementation_steps", [])
    constraints = state["problem"].get("constraints", {})
    public_tests = state["problem"].get("public_tests", [])
    generated_tests = state.get("tests", {}).get("generated_tests", [])
    iteration = state.get("iteration", 0)
    
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
    
    if is_initial:
        # First time: generate complete code
        logger.info("[GenCode] Initial generation (no previous code)")
        
        for attempt in range(1, max_self_attempts + 1):
            prompt = _build_initial_prompt(
                problem_desc, algorithm, steps,
                constraints, public_tests, generated_tests,
                memory_advice=memory_advice,
            )

            code = llm.generate(prompt)
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
        # Patch mode: use SEARCH/REPLACE to fix previous code
        logger.info("[GenCode] Patch mode (fixing previous code)")
        
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
            prompt = _build_patch_prompt(
                prev_code,
                problem_desc,
                algorithm,
                steps,
                specific_failures,
                suggested_fixes,
                feedback_text,
                memory_advice=memory_advice,
            )
            
            llm_response = llm.generate(prompt)
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
            
            # Self-validate patched code
            passed, failures, total_run = _self_validate(code, verify_set, checker_exe)
            
            if passed:
                self_validation_log.append(
                    f"Patch attempt {attempt}: Applied {len(blocks)} edit(s), PASSED all {len(verify_set)} cases"
                )
                logger.info(f"[GenCode] Patch validation passed on attempt {attempt}")
                break
            
            fail_summary = f"Patch attempt {attempt}: Applied {len(blocks)} edit(s), FAILED ({len(failures)} issue(s) in {total_run}/{len(verify_set)} cases)"
            self_validation_log.append(fail_summary)
            logger.info(f"[GenCode] {fail_summary}")
            
            if attempt < max_self_attempts:
                # For next patch attempt, inject validation failures
                feedback_text = _format_self_validation_feedback(failures, total_run, len(verify_set))
                # Update specific_failures with validation failures
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

    return {
        "solution": solution,
        "execution_log": [
            f"Generated C++ code (v{solution['version']}), {llm_calls} LLM call(s)",
            f"  Mode: {'initial' if is_initial else 'patch'}",
            f"  Solve memory items injected: {len(memory_item_ids)}",
            *self_validation_log,
        ],
        "llm_calls": llm_calls,
    }
