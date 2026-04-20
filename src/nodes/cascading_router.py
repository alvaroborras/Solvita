from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
import tempfile
from pathlib import Path
import json

from src.llm import UnifiedLLMClient
from src.nodes.generator_semantic import (
    generate_semantic_test_program,
    repair_semantic_test_program,
)
from src.nodes.generator_stress import (
    generate_stress_test_program,
    repair_stress_test_program,
)
from src.nodes.generator_anti_hash import generate_anti_hash_test_program
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits, cleanup_tempdir

class GeneratorRoute(str, Enum):
    ANTI_HASH = "anti_hash"
    SEMANTIC = "semantic"
    STRESS = "stress"


def classify_generation_failure(error_reason: str) -> str:
    text = (error_reason or "").lower()
    if "compilation failed" in text:
        return "compile_failed"
    if "validation failed" in text:
        return "validator_rejected"
    if "empty output" in text:
        return "empty_output"
    if "execution failed" in text:
        return "runtime_error"
    return "unknown"


def execute_generator_and_validate(
    cpp_source: str,
    validator_exe: Optional[Path],
    problem_limits: Dict[str, Any]
) -> Tuple[bool, str, str]:
    """
    Compiles the generator, runs it, and validates its single stdout output against the validator.
    Returns:
        (is_success, generated_input, error_reason)
    """
    tmpdir = Path(tempfile.mkdtemp())
    try:
        src_path = tmpdir / "gen.cpp"
        exe_path = tmpdir / "gen.exe"
        src_path.write_text(cpp_source, encoding="utf-8")
        
        # 1. Compile Generator
        compiled, comp_out = compile_cpp(src_path, exe_path, limits=ExecutionLimits.hacker_compile())
        if not compiled:
            return False, "", f"Compilation Failed: {comp_out[:200]}"
            
        # 2. Run Generator to produce the test case
        ret, gen_out, gen_err = run_program(
            exe_path,
            limits=ExecutionLimits.hacker_run(),
            truncate_output=False,
        )
        if ret != 0:
            return False, "", f"Generator execution failed (Code {ret}): {gen_err[:200]}"
            
        generated_input = gen_out.strip() + "\n"
        if not generated_input.strip():
            return False, "", "Generator produced empty output."
            
        # 3. Validate against Problem Constraints if validator available
        if validator_exe and validator_exe.exists():
            v_ret, _, v_err = run_program(
                validator_exe, 
                input_text=generated_input, 
                limits=ExecutionLimits.default_run()
            )
            if v_ret != 0:
                reason = (v_err.strip() or f"Validator exit {v_ret}")[:200]
                return False, generated_input, f"Validation Failed: {reason}"
                
        return True, generated_input, ""
    finally:
        cleanup_tempdir(tmpdir, windows_ignore_permission_errors=True)


def cascading_execution_router(
    state: Dict[str, Any],
    llm: UnifiedLLMClient,
    analyst_report: Dict[str, Any],
    max_retries: int = 3,
    memory_advice: str = "",
    messages_history: list = None,
) -> Tuple[str, str, List[str], List[Dict[str, str]]]:
    """
    Implements the T3.1 Cascading Execution Logic.
    Returns:
        (route_used, validated_test_input, execution_log, new_messages)
    """
    execution_log = []
    all_new_msgs: List[Dict[str, str]] = []
    history = list(messages_history) if messages_history else []
    tests_data = state.get("tests", {})
    validator_path_str = tests_data.get("validator_exe")
    validator_exe = Path(validator_path_str) if validator_path_str else None
    
    suggested_route = analyst_report.get("suggested_route", "semantic")
    
    # ---- 1. Primary Feature Routing (Anti-Hash Phase) ----
    if suggested_route == "anti_hash":
        logger.info("[Router] Executing Primary Anti-Hash Generator")
        execution_log.append("Router: Attempting Anti-Hash generator.")
        cpp_source, gen_msgs = generate_anti_hash_test_program(state, llm, analyst_report, messages_history=history)
        all_new_msgs.extend(gen_msgs)
        history.extend(gen_msgs)
        ok, result, err = execute_generator_and_validate(cpp_source, validator_exe, state.get("problem", {}))
        if ok:
            execution_log.append("Router: Anti-Hash generation successful.")
            return GeneratorRoute.ANTI_HASH.value, result, execution_log, all_new_msgs
        else:
            execution_log.append(f"Router: Anti-Hash failed ({err}). Downgrading to Semantic.")
            logger.warning("[Router] Anti-Hash Failed. Downgrading to Semantic route.")

    # ---- 2. Standard Semantic Phase ----
    # Runs if suggested==semantic OR if anti-hash downgraded
    logger.info("[Router] Entering Semantic Generator loop.")
    semantic_log = []
    semantic_feedback = ""
    previous_generated_input = ""
    last_generator_code = ""
    failure_kind = ""
    failure_reason = ""
    
    for attempt in range(1, max_retries + 1):
        execution_log.append(f"Router: Semantic generation attempt {attempt}/{max_retries}.")
        if attempt == 1 or not last_generator_code:
            cpp_source, gen_msgs = generate_semantic_test_program(
                state, llm, analyst_report,
                memory_advice=memory_advice,
                previous_attempt_issues=semantic_feedback,
                previous_generated_input=previous_generated_input,
                messages_history=history,
            )
        else:
            cpp_source, gen_msgs = repair_semantic_test_program(
                state, llm, analyst_report,
                last_generator_code=last_generator_code,
                failure_kind=failure_kind,
                failure_reason=failure_reason,
                previous_attempt_issues=semantic_feedback,
                previous_generated_input=previous_generated_input,
                memory_advice=memory_advice,
                messages_history=history,
            )
        all_new_msgs.extend(gen_msgs)
        history.extend(gen_msgs)
        ok, result, err = execute_generator_and_validate(cpp_source, validator_exe, state.get("problem", {}))

        if ok:
            execution_log.append("Router: Semantic generation successful.")
            return GeneratorRoute.SEMANTIC.value, result, execution_log, all_new_msgs
            
        semantic_log.append(f"Attempt {attempt} failed: {err}")
        logger.debug(f"[Router] Semantic attempt {attempt} failed: {err}")
        last_generator_code = cpp_source
        previous_generated_input = result
        failure_reason = err
        failure_kind = classify_generation_failure(err)
        current_feedback = f"[{failure_kind}] {err}" if failure_kind else err
        if result:
            current_feedback += f"\nGenerated input sample:\n{result[:200]}"
        semantic_feedback = f"{semantic_feedback}\n{current_feedback}".strip()
        
    execution_log.append("\n".join(semantic_log))
    execution_log.append("Router: All Semantic attempts failed. Downgrading to Stress Fuzzer.")
    logger.warning(f"[Router] Semantic failed {max_retries} times. Downgrading to Stress Test Fuzzer.")

    # ---- 3. Fallback Stress Test Phase ----
    stress_feedback = ""
    stress_previous_generated_input = ""
    stress_last_generator_code = ""
    stress_failure_kind = ""
    stress_failure_reason = ""

    for attempt in range(1, max_retries + 1):
        execution_log.append(f"Router: Stress generation attempt {attempt}/{max_retries}.")
        if attempt == 1 or not stress_last_generator_code:
            cpp_source, gen_msgs = generate_stress_test_program(state, llm, messages_history=history)
        else:
            cpp_source, gen_msgs = repair_stress_test_program(
                state, llm,
                last_generator_code=stress_last_generator_code,
                failure_kind=stress_failure_kind,
                failure_reason=stress_failure_reason,
                previous_attempt_issues=stress_feedback,
                previous_generated_input=stress_previous_generated_input,
                messages_history=history,
            )
        all_new_msgs.extend(gen_msgs)
        history.extend(gen_msgs)

        ok, result, err = execute_generator_and_validate(cpp_source, validator_exe, state.get("problem", {}))

        if ok:
            execution_log.append("Router: Stress generation successful.")
            return GeneratorRoute.STRESS.value, result, execution_log, all_new_msgs

        stress_last_generator_code = cpp_source
        stress_previous_generated_input = result
        stress_failure_reason = err
        stress_failure_kind = classify_generation_failure(err)
        current_feedback = f"[{stress_failure_kind}] {err}" if stress_failure_kind else err
        if result:
            current_feedback += f"\nGenerated input sample:\n{result[:200]}"
        stress_feedback = f"{stress_feedback}\n{current_feedback}".strip()
        execution_log.append(f"Router: Stress attempt {attempt} failed ({err}).")

    execution_log.append(f"Router: CRITICAL. Stress generator fallback also failed: {stress_failure_reason}")
    execution_log.append(
        "ROUTER_META: "
        + json.dumps({"failure_kind": stress_failure_kind, "failure_reason": stress_failure_reason}, ensure_ascii=False)
    )
    logger.error("[Router] Stress fuzzer fallback failed.")
    
    # Total failure
    return "failed", "", execution_log, all_new_msgs
