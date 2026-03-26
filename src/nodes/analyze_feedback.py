"""Analyze Feedback Node - Analyze failures and provide improvement suggestions"""

from typing import Dict, Any, TYPE_CHECKING, List, Optional
from pathlib import Path
import tempfile
from loguru import logger
from src.llm import UnifiedLLMClient
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits
import json
from src.utils.json_utils import parse_json_response
from src.utils.prompt_utils import compact_json_for_prompt, truncate_for_prompt

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


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

    if hack_failures:
        logger.info(f"Analyzing {len(hack_failures)} hack failures")
        return _analyze_hack_failures(
            llm, 
            code, 
            hack_failures, 
            problem_desc, 
            state.get('plan', {}).get('algorithm_choice', ''), 
            state.get('plan', {}).get('implementation_steps', []), 
            state.get('iteration', 0)
        )
    
    # Analyze compilation errors first (higher priority)
    if compilation_errors:
        feedback_dict = _analyze_compilation_errors(llm, code, compilation_errors)
    else:
        # Analyze test failures
        failed_tests = [t for t in test_results if not t.get('passed', False)]
        feedback_dict = _analyze_test_failures(
            llm, code, failed_tests,
            problem_desc, algorithm, steps, iteration, pass_rate
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
        "execution_log": ["✓ Feedback analyzed"],
        "llm_calls": 1,
    }


def _analyze_compilation_errors(llm: UnifiedLLMClient, code: str, errors: list[str]) -> Dict:
    """Analyze compilation errors"""
    error_text = truncate_for_prompt('\n'.join(errors), 5000, "COMPILATION_ERRORS")
    code = truncate_for_prompt(code, 12000, "CODE")
    
    prompt = f"""The following C++ code has compilation errors:

Code:
```cpp
{code}
```

Compilation Errors:
{error_text}

Provide:
1. Root cause of the errors
2. Specific fixes needed
3. Corrected code snippets

Be concise and actionable."""
    
    analysis = llm.generate(prompt)
    
    return {
        'error_type': 'compilation',
        'analysis': analysis,
        'suggested_fixes': [],  # LLM provides fixes in analysis text
    }


def _select_representative_failures(failed_tests: List[Dict], max_count: int = 10) -> List[Dict]:
    """
    Select up to max_count representative failures covering:
    - Different error types (Timeout, RE, WA, Checker)
    - Shortest inputs (traceable)
    - Largest diffs (numeric)
    - Different input scales (small/large)
    """
    if not failed_tests:
        return []
    
    selected = []
    selected_ids = set()
    
    # Helper to add unique test
    def add_test(test):
        test_id = id(test)
        if test_id not in selected_ids:
            selected.append(test)
            selected_ids.add(test_id)
            return True
        return False
    
    # 1. Priority: Different error types
    error_types = {}
    for t in failed_tests:
        error = str(t.get('error') or '')
        if 'Timeout' in error or 'timeout' in error.lower():
            error_types.setdefault('timeout', []).append(t)
        elif t.get('passed') == False and t.get('actual') == '':
            error_types.setdefault('runtime_error', []).append(t)
        elif 'Checker' in error:
            error_types.setdefault('checker', []).append(t)
        else:
            error_types.setdefault('wrong_answer', []).append(t)
    
    # Add one from each error type
    for error_type in ['timeout', 'runtime_error', 'checker', 'wrong_answer']:
        if error_type in error_types and error_types[error_type]:
            add_test(error_types[error_type][0])
            if len(selected) >= max_count:
                return selected
    
    # 2. Priority: Shortest inputs (easiest to trace)
    remaining = [t for t in failed_tests if id(t) not in selected_ids]
    remaining.sort(key=lambda t: len(str(t.get('input', ''))))
    
    for t in remaining[:3]:  # Add up to 3 shortest
        add_test(t)
        if len(selected) >= max_count:
            return selected
    
    # 3. Priority: Largest numeric errors
    remaining = [t for t in failed_tests if id(t) not in selected_ids]
    numeric_errors = []
    for t in remaining:
        try:
            act = float(t.get('actual', 0))
            exp = float(t.get('expected', 0))
            err = abs(act - exp)
            numeric_errors.append((err, t))
        except:
            pass
    
    numeric_errors.sort(key=lambda x: x[0], reverse=True)
    for _, t in numeric_errors[:2]:  # Add up to 2 with largest errors
        add_test(t)
        if len(selected) >= max_count:
            return selected
    
    # 4. Fill remaining slots with diverse input sizes
    remaining = [t for t in failed_tests if id(t) not in selected_ids]
    if remaining:
        # Sort by input length and pick evenly spaced
        remaining.sort(key=lambda t: len(str(t.get('input', ''))))
        step = max(1, len(remaining) // (max_count - len(selected)))
        for i in range(0, len(remaining), step):
            add_test(remaining[i])
            if len(selected) >= max_count:
                break
    
    return selected


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
    
    # Pick smallest failing test
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
            
            # Compile with sanitizers
            ok, compile_log = compile_cpp(
                src_path, exe_path,
                limits=ExecutionLimits.diagnostic_compile(),
                diagnostic=True
            )
            
            if not ok:
                return f"Diagnostic compile failed: {compile_log[:500]}"
            
            # Run with sanitizers
            retcode, stdout, stderr = run_program(
                exe_path,
                input_text=test_input,
                limits=ExecutionLimits.default_run()
            )
            
            # Sanitizer output is in stderr
            if stderr and ('sanitizer' in stderr.lower() or 'asan' in stderr.lower() or 'ubsan' in stderr.lower()):
                return f"Sanitizer detected issues:\n{stderr[:1000]}"
            
            return ""
    except Exception as e:
        logger.warning(f"Diagnostic sanitizer failed: {e}")
        return ""


def _analyze_test_failures(
    llm: UnifiedLLMClient, 
    code: str, 
    failed_tests: list[Dict],
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    iteration: int,
    pass_rate: float,
    diagnostic_output: str = ""
) -> Dict:
    """Analyze test failures with full context"""
    if not failed_tests:
        return {'error_type': 'none', 'analysis': 'No failures', 'suggested_fixes': [], 'failures': []}
    
    # Smart selection: up to 10 representative failures
    selected_tests = _select_representative_failures(failed_tests, max_count=10)
    error_pattern = _analyze_error_pattern(failed_tests)
    
    # Format failures for prompt
    failure_details = []
    
    for i, test in enumerate(selected_tests):
        inp = str(test.get('input', ''))
        if len(inp) > 500: inp = inp[:500] + "...(truncated)"
        
        failure_details.append(
            f"--- Failure Case {i+1} ---\n"
            f"Input:\n{inp}\n"
            f"Expected Output: {test.get('expected', '')}\n"
            f"Actual Output:   {test.get('actual', '')}\n"
            f"Error Message:   {test.get('error', '')}"
        )
    
    failures_text = '\n\n'.join(failure_details)
    steps_text = '\n'.join([f"- {s}" for s in steps])
    
    # Add diagnostic output if available
    diagnostic_section = ""
    if diagnostic_output:
        diagnostic_section = f"\n## Diagnostic Sanitizer Output\n{truncate_for_prompt(diagnostic_output, 4000, 'DIAGNOSTIC_OUTPUT')}\n"

    problem_desc = truncate_for_prompt(problem_desc, 7000, "PROBLEM_DESC")
    algorithm = truncate_for_prompt(algorithm, 800, "ALGORITHM")
    steps_text = truncate_for_prompt(steps_text, 2000, "STEPS")
    code = truncate_for_prompt(code, 12000, "CODE")
    failures_text = truncate_for_prompt(failures_text, 8000, "FAILURES")
    
    prompt = f"""You are a competitive programming debugging expert. Analyze the following failures and provide CONCRETE fixes.

## Problem Description
{problem_desc}

## Selected Approach
Algorithm: {algorithm}
Steps:
{steps_text}

## Current Status
Iteration: {iteration}
Pass Rate: {pass_rate:.1%}
Total Failed: {len(failed_tests)}
Error Pattern: {error_pattern}

## Current Code
```cpp
{code}
```

## Representative Failures (most important cases to fix)
{failures_text}
{diagnostic_section}
## Your Task
1. Pick the SIMPLEST failure case above. Trace the code execution step-by-step with that input. Track key variables.
2. Identify WHERE and WHY the code produces wrong output.
3. Determine the root cause category: overflow, off-by-one, wrong formula, missing edge case, TLE, etc.
4. Provide SPECIFIC code-level fixes (not vague suggestions).

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
    "analysis": "<detailed step-by-step trace showing where the bug is>",
    "root_cause": "<one-line root cause>",
    "error_pattern": "<category: overflow/off-by-one/wrong-formula/missing-edge-case/tle/other>",
    "suggested_fixes": [
        "<specific fix 1, e.g. 'Change line X: use long long instead of int'>",
        "<specific fix 2, e.g. 'Add special case handling when n==1'>"
    ]
}}"""
    
    analysis = llm.generate(prompt)
    
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

    return {
        'error_type': 'test_failure',
        'failed_count': len(failed_tests),
        'analysis': analysis_text,
        'error_pattern': error_pattern,
        'suggested_fixes': suggested_fixes,
        'failures': normalized_failures,
    }


def _analyze_hack_failures(
    llm: UnifiedLLMClient, 
    code: str, 
    hack_failures: List[Dict],
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    iteration: int
) -> Dict[str, Any]:
    """Analyze failures from the Adversarial Hack Phase"""
    
    failures_text = ""
    for i, fail in enumerate(hack_failures[:3]): # Limit to top 3
        failures_text += f"\n--- Hack Test {i+1} ---\n"
        failures_text += f"Type: {fail.get('type', 'Unknown')}\n"
        failures_text += f"Input:\n{fail.get('input', '')}\n"
        details = []
        if fail.get('expected'):
            details.append(f"Expected:\n{fail.get('expected', '')}")
        if fail.get('output'):
            details.append(f"Actual Output:\n{fail.get('output', '')}") 
        if fail.get('details'):
             details.append(f"Details:\n{fail.get('details', '')}")
        failures_text += "\n".join(details) + "\n"

    prompt = f"""You are a debugging expert. The solution passed all basic tests but FAILED adversarial hack tests.

Problem:
{problem_desc}

Current Algorithm:
{algorithm}

Implementation Steps:
{json.dumps(steps, indent=2)}

Code:
```cpp
{code}
```

HACK FAILURES (The code logic is likely correct for simple cases but fails edge cases):
{failures_text}

Task:
1. Analyze why the code fails these specific hack cases.
2. Identify the root cause (e.g. overflow, edge case, logic hole).
3. Provide a fixed C++ solution.

Return ONLY JSON:
{{
    "analysis": "<analysis of hack failures>",
    "suggested_fixes": ["<fix 1>", "<fix 2>"]
}}
"""
    
    response = llm.generate(prompt)
    
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
        "execution_log": [
            f"Analyzed {len(hack_failures)} hack failures",
            f"Root cause: {analysis_data.get('analysis', '')[:50]}..."
        ],
        "llm_calls": 1,
    }
