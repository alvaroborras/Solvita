"""Analyze Feedback Node - Analyze failures and provide improvement suggestions"""

from typing import Dict, Any, TYPE_CHECKING, List, Optional
from loguru import logger
from src.llm import UnifiedLLMClient
import json

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
    problem_desc = state['problem'].get('description', '')
    algorithm = state.get('plan', {}).get('algorithm_choice', 'Unknown')
    steps = state.get('plan', {}).get('implementation_steps', [])
    iteration = state.get('iteration', 0)
    pass_rate = state['tests'].get('pass_rate', 0.0)
    
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
    }

    return {
        "feedback": feedback,
        "execution_log": ["✓ Feedback analyzed"],
        "llm_calls": 1,
    }


def _analyze_compilation_errors(llm: UnifiedLLMClient, code: str, errors: list[str]) -> Dict:
    """Analyze compilation errors"""
    error_text = '\n'.join(errors)
    
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


def _select_representative_failures(failed_tests: List[Dict], max_count: int = 3) -> List[Dict]:
    """Select representative failures: Public > Shortest Input > Max Error"""
    selected = []
    
    # 1. Priority: Public test failures
    public_fails = [t for t in failed_tests if str(t.get('test_id', '')).startswith('public') or 'public' in str(t.get('input', ''))] # heuristic if test_id not distinct
    # Actually checking test_id usually works if run_tests sets it clearly. 
    # run_tests sets integer test_id. We can't distinguish public easily unless we assume first K are public.
    # But usually public tests are first. Let's pick the very first failure (often a public or simple case).
    
    if failed_tests:
        selected.append(failed_tests[0])
    
    # 2. Priority: Shortest input (easiest to trace)
    remaining = [t for t in failed_tests if t not in selected]
    # Sort by input length
    remaining.sort(key=lambda t: len(str(t.get('input', ''))))
    
    if remaining:
        selected.append(remaining[0])
        
    # 3. Priority: Largest numeric error (if applicable)
    # Try to find one with large diff if possible
    remaining = [t for t in failed_tests if t not in selected]
    max_err_test = None
    max_err_val = -1.0
    
    for t in remaining:
        try:
            act = float(t.get('actual', 0))
            exp = float(t.get('expected', 0))
            err = abs(act - exp)
            if err > max_err_val:
                max_err_val = err
                max_err_test = t
        except:
            pass
            
    if max_err_test:
        selected.append(max_err_test)
    elif remaining:
        # Fallback: just take next one
        selected.append(remaining[0])
        
    return selected[:max_count]


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


def _analyze_test_failures(
    llm: UnifiedLLMClient, 
    code: str, 
    failed_tests: list[Dict],
    problem_desc: str,
    algorithm: str,
    steps: List[str],
    iteration: int,
    pass_rate: float
) -> Dict:
    """Analyze test failures with full context"""
    if not failed_tests:
        return {'error_type': 'none', 'analysis': 'No failures', 'suggested_fixes': [], 'failures': []}
    
    # Smart selection
    selected_tests = _select_representative_failures(failed_tests)
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
        json_str = analysis.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        
        parsed = json.loads(json_str)
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
        # Simple extraction
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
            
        analysis_data = json.loads(json_str)
    except Exception:
        analysis_data = {"analysis": "Failed to parse analysis", "suggested_fixes": []}
        
    return {
        "feedback": {
            "type": "hack_failure",
            "failures": hack_failures,
            "analysis": analysis_data.get("analysis", ""),
            "generated_at": iteration
        },
        "suggested_fixes": analysis_data.get("suggested_fixes", []),
        "execution_log": [
            f"Analyzed {len(hack_failures)} hack failures",
            f"Root cause: {analysis_data.get('analysis', '')[:50]}..."
        ]
    }
