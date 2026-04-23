"""Analyze Feedback Node - Analyze failures and provide improvement suggestions"""

from collections import Counter
from typing import Dict, Any, TYPE_CHECKING, List, Optional, Tuple
from pathlib import Path
import tempfile
from loguru import logger
from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.nodes._chat_utils import build_chat_compaction_context, chat_with_history
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits
import json
from src.utils.json_utils import parse_json_response
from src.utils.prompt_utils import compact_json_for_prompt, truncate_for_prompt
from src.utils.prompt_templates import render_template

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _log_prompt(stage: str, prompt: str, compact: bool) -> None:
    logger.debug(f"[PROMPT_BODY:{stage}] compact={int(compact)}\n{prompt}")


def _generate_feedback_with_retry(
    llm: UnifiedLLMClient,
    build_prompt,
    *args,
    _messages_history: Optional[list] = None,
    _stage: str = "analyze_feedback",
    _compaction_context: Optional[Dict[str, Any]] = None,
    _compaction_config: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> tuple | str:
    """Call feedback prompt builder with optional threaded conversation history."""
    history = _messages_history if _messages_history is not None else []
    prompt = build_prompt(*args, compact=False, **kwargs)
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
        compact_prompt = build_prompt(*args, compact=True, **kwargs)
        _log_prompt(_stage, compact_prompt, compact=True)
        logger.warning("[AnalyzeFeedback] Prompt exceeded max tokens, retrying with compact prompt")
        if _messages_history is None:
            return llm.generate(compact_prompt)
        return chat_with_history(
            llm,
            history,
            compact_prompt,
            compaction_context=_compaction_context,
            compaction_config=_compaction_config,
        )


def _call_feedback_with_history(
    llm: UnifiedLLMClient,
    build_prompt,
    *args,
    messages_history: Optional[list] = None,
    _stage: str = "analyze_feedback",
    _compaction_context: Optional[Dict[str, Any]] = None,
    _compaction_config: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
    result = _generate_feedback_with_retry(
        llm,
        build_prompt,
        *args,
        _messages_history=messages_history,
        _stage=_stage,
        _compaction_context=_compaction_context,
        _compaction_config=_compaction_config,
        **kwargs,
    )
    from src.nodes._chat_utils import normalize_chat_history_result
    return normalize_chat_history_result(result)


def analyze_feedback_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Analyze test failures and compilation errors

    Provides:
    - Root cause analysis
    - Suggested fixes
    - Error patterns
    """
    logger.info("[Node] Analyzing feedback from failures")

    # Get failure information
    code = state['solution'].get('code', '')
    compilation_errors = state['solution'].get('compilation_errors', [])
    test_results = state['tests'].get('test_results', [])

    # [NEW] Check for Hack Failures
    hack_failures = state.get('hack_failures', [])

    # Get context information
    # Prefer canonical problem representation if available
    canonical = state['problem'].get('canonical', {})
    if canonical:
        problem_desc = f"""Objective: {canonical.get('objective', '')}
Constraints: {json.dumps(canonical.get('constraints', {}), indent=2)}
Required Properties: {canonical.get('required_properties', [])}"""
    else:
        problem_desc = state['problem'].get('description', '')

    algorithm = state.get('plan', {}).get('algorithm_choice', 'Unknown')
    steps = state.get('plan', {}).get('implementation_steps', [])
    iteration = state.get('iteration', 0)
    pass_rate = state['tests'].get('pass_rate', 0.0)
    solution_version = state.get('solution', {}).get('version', 0)
    pending_execution = state.get('tests', {}).get('pending_execution', False)

    fingerprint = (
        f"it={iteration}|v={solution_version}|pass={pass_rate:.6f}|"
        f"tests={len(test_results)}|comp_errs={len(compilation_errors)}|"
        f"hack={len(hack_failures)}"
    )
    existing_fingerprint = state.get('feedback', {}).get('fingerprint')

    if pending_execution and not compilation_errors and not hack_failures:
        logger.debug("Skipping feedback: tests pending execution")
        return {
            "execution_log": ["Feedback skipped: tests pending execution"],
            "llm_calls": 0,
            "skip_generate_code": True,
        }

    if existing_fingerprint == fingerprint:
        logger.debug("Skipping feedback: already analyzed for current results")
        return {
            "execution_log": ["Feedback skipped: already analyzed"],
            "llm_calls": 0,
            "skip_generate_code": True,
        }

    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])
    history = list(state.get("messages", []))
    compaction_context = build_chat_compaction_context(state, node_name="analyze_feedback")
    compaction_config = state.get("config")

    if hack_failures:
        logger.info(f"Analyzing {len(hack_failures)} hack failures")
        return _analyze_hack_failures(
            llm,
            code,
            hack_failures,
            problem_desc,
            state.get('plan', {}).get('algorithm_choice', ''),
            state.get('plan', {}).get('implementation_steps', []),
            state.get('iteration', 0),
            messages_history=history,
            compaction_context=compaction_context,
            compaction_config=compaction_config,
        )

    # Analyze compilation errors first (higher priority)
    if compilation_errors:
        feedback_dict, new_msgs = _analyze_compilation_errors(
            llm,
            code,
            compilation_errors,
            messages_history=history,
            compaction_context=compaction_context,
            compaction_config=compaction_config,
        )
    else:
        # Analyze test failures
        failed_tests = [t for t in test_results if not t.get('passed', False)]
        feedback_dict, new_msgs = _analyze_test_failures(
            llm,
            code,
            failed_tests,
            problem_desc,
            algorithm,
            steps,
            iteration,
            pass_rate,
            messages_history=history,
            compaction_context=compaction_context,
            compaction_config=compaction_config,
        )

    # Build feedback dict (avoiding FeedbackData import for circular dep fix)
    feedback = {
        "feedback": feedback_dict,
        "suggested_fixes": feedback_dict.get('suggested_fixes', []),
        "error_pattern": feedback_dict.get('error_pattern', ''),
        "fingerprint": fingerprint,
    }

    return {
        "feedback": feedback,
        "messages": new_msgs,
        "execution_log": ["✓ Feedback analyzed"],
        "llm_calls": 1,
    }


def _build_compilation_error_prompt(code: str, errors: list[str], compact: bool = False) -> str:
    """Analyze compilation errors"""
    error_text = truncate_for_prompt('\n'.join(errors), 5000 if not compact else 2000, "COMPILATION_ERRORS")
    code = truncate_for_prompt(code, 12000 if not compact else 5000, "CODE")

    return render_template(
        "analyze_feedback.compilation",
        CODE=code,
        ERROR_TEXT=error_text,
    )


def _analyze_compilation_errors(
    llm: UnifiedLLMClient,
    code: str,
    errors: list[str],
    messages_history: Optional[list] = None,
    compaction_context: Optional[Dict[str, Any]] = None,
    compaction_config: Optional[Dict[str, Any]] = None,
) -> tuple:
    result = _call_feedback_with_history(
        llm,
        _build_compilation_error_prompt,
        code,
        errors,
        messages_history=messages_history,
        _stage="analyze_feedback.compilation",
        _compaction_context=compaction_context,
        _compaction_config=compaction_config,
    )
    if messages_history is None:
        analysis = result
        new_msgs = []
    else:
        analysis, new_msgs, persisted_messages = result
        messages_history[:] = persisted_messages
    feedback = {
        'error_type': 'compilation',
        'analysis': analysis,
        'suggested_fixes': [],
    }
    if messages_history is None:
        return feedback
    return feedback, new_msgs


def _normalize_output_tokens(text: Any) -> List[str]:
    return str(text or "").split()



def _normalize_space(text: Any) -> str:
    return " ".join(str(text or "").split())



def _parse_numeric_tokens(text: Any) -> Optional[List[float]]:
    tokens = _normalize_output_tokens(text)
    if not tokens:
        return None
    try:
        return [float(token) for token in tokens]
    except ValueError:
        return None



def _classify_failure_status(test: Dict[str, Any]) -> str:
    error = str(test.get("error") or "")
    error_lower = error.lower()
    actual_text = str(test.get("actual", "") or "").strip()

    if any(token in error_lower for token in ["memory limit", "bad_alloc", "out of memory", "oom"]):
        return "memory_limit_exceeded"
    if "timeout" in error_lower or "time limit" in error_lower:
        return "timeout"
    if "checker" in error_lower or "presentation" in error_lower or "invalid output" in error_lower:
        return "checker"
    if any(
        token in error_lower
        for token in [
            "runtime error",
            "segmentation fault",
            "sigsegv",
            "abort",
            "assert",
            "floating point exception",
            "sigfpe",
            "asan",
            "ubsan",
            "sanitizer",
            "killed",
        ]
    ):
        return "runtime_error"
    if not actual_text and error:
        return "runtime_error"
    return "wrong_answer"



def _classify_repair_subtype(test: Dict[str, Any]) -> str:
    status = _classify_failure_status(test)
    error = str(test.get("error") or "")
    error_lower = error.lower()
    input_text = str(test.get("input", "") or "")
    expected_text = str(test.get("expected", "") or "")
    actual_text = str(test.get("actual", "") or "")
    expected_tokens = _normalize_output_tokens(expected_text)
    actual_tokens = _normalize_output_tokens(actual_text)

    if status == "memory_limit_exceeded":
        return "mle_large_allocation"
    if status == "timeout":
        return "tle_small_input" if len(input_text) <= 48 else "tle_full_input_only"
    if status == "runtime_error":
        if any(
            token in error_lower
            for token in ["segmentation fault", "sigsegv", "asan", "ubsan", "sanitizer", "floating point exception", "sigfpe"]
        ):
            return "re_signal_crash"
        return "re_exception_or_abort"
    if status == "checker":
        if expected_text and actual_text and _normalize_space(expected_text) == _normalize_space(actual_text) and expected_text != actual_text:
            return "wa_formatting"
        if expected_tokens and actual_tokens and Counter(expected_tokens) == Counter(actual_tokens) and expected_tokens != actual_tokens:
            return "wa_ordering"
        return "wa_checker_semantics"

    if not actual_text.strip():
        return "wa_empty_output"
    if expected_text and _normalize_space(expected_text) == _normalize_space(actual_text) and expected_text != actual_text:
        return "wa_formatting"
    if expected_tokens and actual_tokens and len(actual_tokens) < len(expected_tokens) and expected_tokens[:len(actual_tokens)] == actual_tokens:
        return "wa_partial_output"
    if expected_tokens and actual_tokens and Counter(expected_tokens) == Counter(actual_tokens) and expected_tokens != actual_tokens:
        return "wa_ordering"

    actual_numbers = _parse_numeric_tokens(actual_text)
    expected_numbers = _parse_numeric_tokens(expected_text)
    if actual_numbers and expected_numbers and len(actual_numbers) == len(expected_numbers):
        diffs = [actual - expected for actual, expected in zip(actual_numbers, expected_numbers)]
        nonzero_diffs = [diff for diff in diffs if abs(diff) > 1e-9]
        if nonzero_diffs:
            if all(diff < 0 for diff in nonzero_diffs):
                return "wa_numeric_too_small"
            if all(diff > 0 for diff in nonzero_diffs):
                return "wa_numeric_too_large"
            return "wa_numeric_mixed"

    if len(input_text) <= 48:
        return "wa_edge_case_small"
    return "wa_logic_or_formula"



def _traceability_key(test: Dict[str, Any]) -> tuple:
    subtype = _classify_repair_subtype(test)
    status = _classify_failure_status(test)
    input_len = len(str(test.get("input", "") or ""))

    subtype_rank = {
        "wa_edge_case_small": 0,
        "wa_formatting": 0,
        "wa_ordering": 0,
        "wa_checker_semantics": 0,
        "wa_empty_output": 1,
        "wa_partial_output": 1,
        "wa_numeric_too_small": 1,
        "wa_numeric_too_large": 1,
        "wa_numeric_mixed": 1,
        "re_signal_crash": 2,
        "tle_small_input": 3,
        "re_exception_or_abort": 3,
        "wa_logic_or_formula": 4,
        "tle_full_input_only": 4,
        "mle_large_allocation": 5,
    }
    status_rank = {
        "checker": 0,
        "wrong_answer": 1,
        "runtime_error": 2,
        "timeout": 3,
        "memory_limit_exceeded": 4,
    }
    return (
        subtype_rank.get(subtype, 9),
        input_len,
        status_rank.get(status, 9),
    )



def _select_representative_failures(failed_tests: List[Dict], max_count: int = 10) -> List[Dict]:
    """
    Select up to max_count representative failures, with smallest traceable
    counterexamples first while preserving coverage across judge-status and
    repair-subtype buckets.
    """
    if not failed_tests:
        return []

    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    def add_test(test: Dict[str, Any]) -> bool:
        test_id = id(test)
        if test_id in selected_ids:
            return False
        selected.append(test)
        selected_ids.add(test_id)
        return True

    for test in sorted(failed_tests, key=_traceability_key)[:2]:
        add_test(test)
        if len(selected) >= max_count:
            return selected

    status_priority = ["checker", "wrong_answer", "runtime_error", "timeout", "memory_limit_exceeded"]
    for status in status_priority:
        bucket = [test for test in failed_tests if _classify_failure_status(test) == status]
        if bucket:
            add_test(min(bucket, key=_traceability_key))
            if len(selected) >= max_count:
                return selected

    informative_subtypes = {
        "wa_numeric_too_small",
        "wa_numeric_too_large",
        "wa_numeric_mixed",
        "wa_partial_output",
        "wa_empty_output",
        "wa_formatting",
        "wa_ordering",
        "wa_checker_semantics",
        "re_signal_crash",
        "re_exception_or_abort",
        "tle_small_input",
        "mle_large_allocation",
    }
    subtype_buckets: Dict[str, List[Dict[str, Any]]] = {}
    for test in failed_tests:
        subtype = _classify_repair_subtype(test)
        if subtype in informative_subtypes:
            subtype_buckets.setdefault(subtype, []).append(test)

    ordered_subtypes = sorted(
        subtype_buckets,
        key=lambda subtype: _traceability_key(min(subtype_buckets[subtype], key=_traceability_key)),
    )
    for subtype in ordered_subtypes:
        add_test(min(subtype_buckets[subtype], key=_traceability_key))
        if len(selected) >= max_count:
            return selected

    remaining = [test for test in failed_tests if id(test) not in selected_ids]
    remaining.sort(key=lambda test: (_traceability_key(test), len(str(test.get("error", "") or ""))))
    for test in remaining:
        add_test(test)
        if len(selected) >= max_count:
            break

    return selected



def _summarize_failed_tests(failed_tests: List[Dict], max_examples_per_type: int = 3) -> Dict[str, Any]:
    """Build aggregate failure statistics for patch prompting."""
    if not failed_tests:
        return {
            "total_failed": 0,
            "judge_status_counts": {},
            "error_type_counts": {},
            "repair_subtype_counts": {},
            "input_length": {"min": 0, "max": 0, "avg": 0},
            "representative_examples": {},
            "numeric_diff": {},
        }

    status_counts: Counter[str] = Counter()
    subtype_counts: Counter[str] = Counter()
    input_lengths: List[int] = []
    type_examples: Dict[str, List[Dict[str, Any]]] = {}
    numeric_diffs: List[float] = []

    for test in failed_tests:
        status = _classify_failure_status(test)
        subtype = _classify_repair_subtype(test)
        status_counts[status] += 1
        subtype_counts[subtype] += 1
        input_lengths.append(len(str(test.get("input", ""))))

        bucket = type_examples.setdefault(status, [])
        if len(bucket) < max_examples_per_type:
            bucket.append(
                {
                    "input": truncate_for_prompt(str(test.get("input", "")), 240, "AGG_FAIL_INPUT"),
                    "expected": truncate_for_prompt(str(test.get("expected", "")), 160, "AGG_FAIL_EXPECTED"),
                    "actual": truncate_for_prompt(str(test.get("actual", "")), 160, "AGG_FAIL_ACTUAL"),
                    "error": truncate_for_prompt(str(test.get("error", "")), 160, "AGG_FAIL_ERROR"),
                    "repair_subtype": subtype,
                }
            )

        actual_numbers = _parse_numeric_tokens(test.get("actual", ""))
        expected_numbers = _parse_numeric_tokens(test.get("expected", ""))
        if actual_numbers and expected_numbers and len(actual_numbers) == len(expected_numbers):
            numeric_diffs.extend(actual - expected for actual, expected in zip(actual_numbers, expected_numbers))

    avg_len = sum(input_lengths) / len(input_lengths) if input_lengths else 0.0
    numeric_summary: Dict[str, Any] = {}
    if numeric_diffs:
        numeric_summary = {
            "count": len(numeric_diffs),
            "avg_diff": sum(numeric_diffs) / len(numeric_diffs),
            "min_diff": min(numeric_diffs),
            "max_diff": max(numeric_diffs),
        }

    status_counts_dict = dict(status_counts)
    return {
        "total_failed": len(failed_tests),
        "judge_status_counts": status_counts_dict,
        "error_type_counts": status_counts_dict,
        "repair_subtype_counts": dict(subtype_counts),
        "input_length": {
            "min": min(input_lengths) if input_lengths else 0,
            "max": max(input_lengths) if input_lengths else 0,
            "avg": round(avg_len, 2),
        },
        "representative_examples": type_examples,
        "numeric_diff": numeric_summary,
    }


def _analyze_error_pattern(failed_tests: List[Dict]) -> str:
    """Analyze error pattern: larger/smaller/random"""
    numeric_diffs = []
    valid_count = 0

    for t in failed_tests:
        try:
            actual = float(t.get('actual', '').strip())
            expected = float(t.get('expected', '').strip())
            numeric_diffs.append(actual - expected)
            valid_count += 1
        except (ValueError, TypeError):
            continue

    if valid_count < 3:
        return "Non-numeric or mixed errors"

    avg_diff = sum(numeric_diffs) / len(numeric_diffs)
    all_smaller = all(d < -1e-9 for d in numeric_diffs)
    all_larger = all(d > 1e-9 for d in numeric_diffs)

    if all_smaller:
        return f"Outputs consistently smaller than expected (avg diff: {avg_diff:.4g}). Possible overly strict constraints or rounding down."
    elif all_larger:
        return f"Outputs consistently larger than expected (avg diff: {avg_diff:.4g}). Possible loose constraints or rounding up."
    else:
        return f"Outputs vary (avg diff: {avg_diff:.4g}). Likely logic error or edge case handling."


def _run_diagnostic_sanitizer(code: str, failed_tests: List[Dict]) -> str:
    """
    Run diagnostic compilation with sanitizers on smallest failing test.

    Returns sanitizer output or empty string if no useful info.
    """
    if not failed_tests or not code:
        return ""

    smallest_test = min(failed_tests, key=lambda t: len(str(t.get('input', ''))))
    test_input = smallest_test.get('input', '')

    if not test_input:
        return ""

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src_path = tmp / "diagnostic.cpp"
            exe_path = tmp / "diagnostic.exe"

            src_path.write_text(code, encoding="utf-8")

            ok, compile_log = compile_cpp(
                src_path, exe_path,
                limits=ExecutionLimits.diagnostic_compile(),
                diagnostic=True
            )

            if not ok:
                return f"Diagnostic compile failed: {compile_log[:500]}"

            retcode, stdout, stderr = run_program(
                exe_path,
                input_text=test_input,
                limits=ExecutionLimits.default_run()
            )

            if stderr and ('sanitizer' in stderr.lower() or 'asan' in stderr.lower() or 'ubsan' in stderr.lower()):
                return f"Sanitizer detected issues:\n{stderr[:1000]}"

            return ""
    except Exception as e:
        logger.warning(f"Diagnostic sanitizer failed: {e}")
        return ""


def _build_test_failure_prompt(
    code: str,
    failed_tests: list[Dict],
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    iteration: int,
    pass_rate: float,
    diagnostic_output: str = "",
    compact: bool = False,
) -> str:
    selected_tests = _select_representative_failures(failed_tests, max_count=10 if not compact else 5)
    error_pattern = _analyze_error_pattern(failed_tests)
    failure_details = []
    for i, test in enumerate(selected_tests):
        inp = truncate_for_prompt(str(test.get('input', '')), 500 if not compact else 180, f"FAIL_INPUT_{i+1}")
        expected = truncate_for_prompt(str(test.get('expected', '')), 300 if not compact else 120, f"FAIL_EXPECTED_{i+1}")
        actual = truncate_for_prompt(str(test.get('actual', '')), 300 if not compact else 120, f"FAIL_ACTUAL_{i+1}")
        error = truncate_for_prompt(str(test.get('error', '')), 300 if not compact else 120, f"FAIL_ERROR_{i+1}")
        failure_details.append(
            f"--- Failure Case {i+1} ---\n"
            f"Input:\n{inp}\n"
            f"Expected Output: {expected}\n"
            f"Actual Output:   {actual}\n"
            f"Error Message:   {error}"
        )

    failures_text = '\n\n'.join(failure_details)
    steps_text = '\n'.join([f"- {s}" for s in steps])
    diagnostic_section = ""
    if diagnostic_output:
        diagnostic_section = f"\n## Diagnostic Sanitizer Output\n{truncate_for_prompt(diagnostic_output, 4000 if not compact else 1500, 'DIAGNOSTIC_OUTPUT')}\n"

    problem_desc = truncate_for_prompt(problem_desc, 7000 if not compact else 3000, "PROBLEM_DESC")
    algorithm = truncate_for_prompt(algorithm, 800 if not compact else 400, "ALGORITHM")
    steps_text = truncate_for_prompt(steps_text, 2000 if not compact else 800, "STEPS")
    code = truncate_for_prompt(code, 12000 if not compact else 5000, "CODE")
    failures_text = truncate_for_prompt(failures_text, 8000 if not compact else 2500, "FAILURES")

    return render_template(
        "analyze_feedback.test_failure",
        PROBLEM_DESC=problem_desc,
        ALGORITHM=algorithm,
        STEPS_TEXT=steps_text,
        ITERATION=str(iteration),
        PASS_RATE=f"{pass_rate:.1%}",
        FAILED_COUNT=str(len(failed_tests)),
        ERROR_PATTERN=error_pattern,
        CODE=code,
        FAILURES_TEXT=failures_text,
        DIAGNOSTIC_SECTION=diagnostic_section,
    )


def _analyze_test_failures(
    llm: UnifiedLLMClient,
    code: str,
    failed_tests: list[Dict],
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    iteration: int,
    pass_rate: float,
    diagnostic_output: str = "",
    messages_history: Optional[list] = None,
    compaction_context: Optional[Dict[str, Any]] = None,
    compaction_config: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Analyze test failures with full context. Returns (feedback_dict, new_messages)."""
    if not failed_tests:
        return {'error_type': 'none', 'analysis': 'No failures', 'suggested_fixes': [], 'failures': []}, []
    selected_tests = _select_representative_failures(failed_tests, max_count=10)
    error_pattern = _analyze_error_pattern(failed_tests)
    result = _call_feedback_with_history(
        llm,
        _build_test_failure_prompt,
        code,
        failed_tests,
        problem_desc,
        algorithm,
        steps,
        iteration,
        pass_rate,
        diagnostic_output,
        messages_history=messages_history,
        _stage="analyze_feedback.test_failure",
        _compaction_context=compaction_context,
        _compaction_config=compaction_config,
    )
    if messages_history is None:
        analysis = result
        new_msgs = []
    else:
        analysis, new_msgs, persisted_messages = result
        messages_history[:] = persisted_messages
    
    # Parse structured response
    try:
        parsed = parse_json_response(analysis)
        analysis_text = parsed.get("analysis", analysis)
        error_pattern = parsed.get("error_pattern", error_pattern)
        suggested_fixes = parsed.get("suggested_fixes", [])
    except Exception:
        # Fallback: use raw analysis text
        analysis_text = analysis
        suggested_fixes = []

    # Normalize failures for generate_code consumption
    normalized_failures = []
    for test in selected_tests:
        normalized_failures.append({
            "type": "Test Failure",
            "input": test.get("input", ""),
            "expected": test.get("expected", ""),
            "output": test.get("actual", ""),
            "details": test.get("error", ""),
        })

    aggregate_summary = _summarize_failed_tests(failed_tests)
    return {
        'error_type': 'test_failure',
        'failed_count': len(failed_tests),
        'analysis': analysis_text,
        'error_pattern': error_pattern,
        'suggested_fixes': suggested_fixes,
        'failures': normalized_failures,
        'aggregate_summary': aggregate_summary,
    }, new_msgs


def _analyze_hack_failures(
    llm: UnifiedLLMClient,
    code: str,
    hack_failures: List[Dict],
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    iteration: int,
    messages_history: Optional[list] = None,
    compaction_context: Optional[Dict[str, Any]] = None,
    compaction_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Analyze failures from the Adversarial Hack Phase"""

    def _build_hack_failure_prompt(compact: bool = False) -> str:
        failures_text = ""
        for i, fail in enumerate(hack_failures[:3]):  # Limit to top 3
            failures_text += f"\n--- Hack Test {i+1} ---\n"
            failures_text += f"Type: {fail.get('type', 'Unknown')}\n"
            failures_text += f"Input:\n{truncate_for_prompt(fail.get('input', ''), 300 if not compact else 150, f'HACK_INPUT_{i+1}')}\n"
            details = []
            if fail.get('expected'):
                details.append(
                    f"Expected:\n{truncate_for_prompt(fail.get('expected', ''), 200 if not compact else 100, f'HACK_EXPECTED_{i+1}')}"
                )
            if fail.get('output'):
                details.append(
                    f"Actual Output:\n{truncate_for_prompt(fail.get('output', ''), 200 if not compact else 100, f'HACK_OUTPUT_{i+1}')}"
                )
            if fail.get('details'):
                details.append(
                    f"Details:\n{truncate_for_prompt(fail.get('details', ''), 200 if not compact else 100, f'HACK_DETAILS_{i+1}')}"
                )
            failures_text += "\n".join(details) + "\n"

        compact_problem_desc = truncate_for_prompt(problem_desc, 7000 if not compact else 3000, "PROBLEM_DESC")
        compact_algorithm = truncate_for_prompt(algorithm, 800 if not compact else 300, "ALGORITHM")
        compact_code = truncate_for_prompt(code, 12000 if not compact else 5000, "CODE")
        steps_json = compact_json_for_prompt(steps, 2000 if not compact else 800, "STEPS")
        compact_failures = truncate_for_prompt(failures_text, 6000 if not compact else 2000, "HACK_FAILURES")

        return render_template(
            "analyze_feedback.hack_failure",
            PROBLEM_DESC=compact_problem_desc,
            ALGORITHM=compact_algorithm,
            STEPS_JSON=steps_json,
            CODE=compact_code,
            HACK_FAILURES_TEXT=compact_failures,
        )

    response, new_msgs, persisted_messages = _call_feedback_with_history(
        llm,
        _build_hack_failure_prompt,
        messages_history=messages_history,
        _stage="analyze_feedback.hack_failure",
        _compaction_context=compaction_context,
        _compaction_config=compaction_config,
    )
    if messages_history is not None:
        messages_history[:] = persisted_messages
    
    try:
        analysis_data = parse_json_response(response)
    except Exception:
        analysis_data = {"analysis": "Failed to parse analysis", "suggested_fixes": []}
    
    # Build feedback_dict (inner structure)
    feedback_dict = {
        "type": "hack_failure",
        "failures": hack_failures,
        "analysis": analysis_data.get("analysis", ""),
        "suggested_fixes": analysis_data.get("suggested_fixes", []),
        "error_pattern": "hack_failure",  # Add to inner for generate_code to read
        "generated_at": iteration
    }
    
    # Build feedback (outer structure) - matching the pattern in analyze_feedback_node
    feedback = {
        "feedback": feedback_dict,
        "suggested_fixes": feedback_dict.get("suggested_fixes", []),
        "error_pattern": "hack_failure",  # Hack failures are a distinct pattern
    }
    
    return {
        "feedback": feedback,
        "messages": new_msgs,
        "execution_log": [
            f"Analyzed {len(hack_failures)} hack failures",
            f"Root cause: {analysis_data.get('analysis', '')[:50]}..."
        ],
        "llm_calls": 1,
    }
