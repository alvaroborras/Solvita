"""Generate Code Node - Generate C++ solution code with lightweight self-validation"""

import json
import tempfile
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from loguru import logger
from src.llm import UnifiedLLMClient
from src.utils.cpp_execution import sanitize_cpp, compile_cpp, run_program, run_checker


def _build_prompt(
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    constraints: Dict[str, Any],
    public_tests: List[Dict],
    generated_tests: List[Dict],
    feedback_text: str,
) -> str:
    """Build the enhanced prompt with constraints, samples, and structured feedback."""

    # Format public tests
    public_block = ""
    if public_tests:
        parts = []
        for i, t in enumerate(public_tests):
            parts.append(f"  Sample {i+1}:")
            parts.append(f"    Input:\n{_indent(t.get('input', ''), 6)}")
            parts.append(f"    Output:\n{_indent(t.get('output', ''), 6)}")
        public_block = "Public test cases:\n" + "\n".join(parts)

    # Format constraints
    constraints_block = ""
    if constraints:
        constraints_block = f"Constraints:\n  {json.dumps(constraints, indent=2)}"

    # Format generated test inputs (first 3, input only)
    gen_block = ""
    if generated_tests:
        samples = generated_tests[:3]
        parts = []
        for i, t in enumerate(samples):
            inp = t.get("input", "").strip()
            if len(inp) > 300:
                inp = inp[:300] + "..."
            parts.append(f"  Generated input {i+1}:\n{_indent(inp, 4)}")
        gen_block = (
            "Sample generated inputs (for format/scale reference):\n"
            + "\n".join(parts)
        )

    return f"""Generate a complete C++ solution for this competitive programming problem:

Problem: {problem_desc}

Algorithm to use: {algorithm}

Implementation steps:
{chr(10).join(steps)}

{constraints_block}

{public_block}

{gen_block}

{feedback_text}

Requirements:
- Use standard C++ (C++17)
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Include all necessary headers
- Implement fast I/O
- Handle all edge cases
- Optimize for time complexity

Generate ONLY the complete C++ code, no explanations."""


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

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_path = tmp / "solution.cpp"
        exe_path = tmp / "solution.exe"
        src_path.write_text(code, encoding="utf-8")

        ok, compile_log = compile_cpp(src_path, exe_path, timeout=10)
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
                retcode, stdout, stderr = run_program(exe_path, input_text=inp, timeout=2)
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

            if checker_exe and checker_exe.exists():
                # Use Special Checker
                input_file = tmp / f"input_{i}.txt"
                output_file = tmp / f"output_{i}.txt"
                answer_file = tmp / f"answer_{i}.txt"
                
                input_file.write_text(inp, encoding="utf-8")
                output_file.write_text(stdout, encoding="utf-8") # Checker needs raw stdout usually
                answer_file.write_text(expected, encoding="utf-8")
                
                chk_ok, chk_msg = run_checker(checker_exe, input_file, output_file, answer_file)
                passed_test = chk_ok
                if not passed_test:
                    error_msg = f"Checker: {chk_msg}"
            else:
                passed_test = (actual == expected)
                if not passed_test:
                    error_msg = f"Expected '{expected[:50]}...', got '{actual[:50]}...'"

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

    lines.append("Please fix these issues and regenerate the code.")
    return "\n".join(lines)


def generate_code_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Generate C++ solution code using LLM with lightweight self-validation.

    Responsibilities:
    - Generate C++ code based on problem description, algorithm plan, and tests
    - Lightweight self-validation: compile + run public + up to 5 generated tests
    - If validation fails, retry up to 3 times before returning last attempt

    Note: Full testing happens in run_tests_node. This is just a quick check.
    """
    logger.info(f"[Node] Generating C++ code (version {state['solution'].get('version', 0) + 1})")

    llm = UnifiedLLMClient(state["config"])
    llm_calls = 0

    problem_desc = state["problem"].get("description", "")
    algorithm = state["plan"].get("algorithm_choice", "")
    steps = state["plan"].get("implementation_steps", [])
    constraints = state["problem"].get("constraints", {})
    public_tests = state["problem"].get("public_tests", [])
    generated_tests = state.get("tests", {}).get("generated_tests", [])

    # Build self-validation feedback from previous iteration
    feedback_text = ""
    if state["iteration"] > 0:
        feedback = state.get("feedback", {}).get("feedback", {})
        if feedback:
            feedback_lines = ["Previous attempt issues:"]
            # Extract LLM analysis from analyze_feedback node
            analysis = feedback.get("analysis")
            error_pattern = feedback.get("error_pattern")
            
            if error_pattern:
                feedback_lines.append(f"Error Pattern detected: {error_pattern}")
            
            if analysis:
                feedback_lines.append(f"Analysis of previous failure:\n{analysis}")
            
            # Also try to include raw errors if passed (future proofing), but analysis is primary
            if "compilation_errors" in feedback:
                feedback_lines.append("  Compilation errors:")
                for err in feedback["compilation_errors"]:
                    feedback_lines.append(f"    - {err}")
            # Note: analyze_feedback currently puts analysis in 'analysis' field, 
            # and does not pass raw failed_tests structure. 
            # So the analysis text is the main source of truth.
            
            if error_pattern or analysis:
                feedback_lines.append("\nCRITICAL: Your previous code had the above issues.")
                feedback_lines.append("You MUST fix these specific issues or implement a DIFFERENT approach if the same bug persists.")
            
            feedback_text = "\n".join(feedback_lines)

    # Build verification set (lightweight: public + up to 5 generated)
    verify_set = _build_verification_set(public_tests, generated_tests)
    checker_exe_str = state.get("tests", {}).get("checker_exe")
    checker_exe = Path(checker_exe_str) if checker_exe_str else None

    max_self_attempts = 3
    code = ""
    self_validation_log = []

    for attempt in range(1, max_self_attempts + 1):
        prompt = _build_prompt(
            problem_desc, algorithm, steps,
            constraints, public_tests, generated_tests,
            feedback_text,
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

        # Log failure summary
        fail_summary = f"Self-validation attempt {attempt}: FAILED ({len(failures)} issue(s) in {total_run}/{len(verify_set)} cases)"
        self_validation_log.append(fail_summary)
        logger.info(f"[GenCode] {fail_summary}")

        if attempt < max_self_attempts:
            # Inject failure info into feedback for next attempt
            feedback_text = _format_self_validation_feedback(failures, total_run, len(verify_set))

    # Build solution dict (avoiding SolutionData import for circular dep fix)
    solution = {
        "code": code,
        "version": state["solution"].get("version", 0) + 1,
        "compilation_success": False,
        "compilation_errors": [],
        "executable_path": None,
    }

    return {
        "solution": solution,
        "execution_log": [
            f"Generated C++ code (v{solution['version']}), {llm_calls} LLM call(s)",
            *self_validation_log,
        ],
        "llm_calls": llm_calls,
    }
