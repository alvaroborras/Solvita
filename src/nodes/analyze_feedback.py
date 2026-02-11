"""Analyze Feedback Node - Analyze failures and provide improvement suggestions"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger
from src.llm import UnifiedLLMClient

if TYPE_CHECKING:
    from src.graph.state import SolvitaState, FeedbackData


"""Analyze Feedback Node - Analyze failures and provide improvement suggestions"""

from typing import Dict, Any, TYPE_CHECKING, List, Optional
from loguru import logger
from src.llm import UnifiedLLMClient

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
    
    # Get context information
    problem_desc = state['problem'].get('description', '')
    algorithm = state['plan'].get('algorithm_choice', 'Unknown')
    steps = state['plan'].get('implementation_steps', [])
    iteration = state.get('iteration', 0)
    pass_rate = state['tests'].get('pass_rate', 0.0)
    
    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])
    
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
        return {'error_type': 'none', 'analysis': 'No failures', 'suggested_fixes': []}
    
    # Smart selection
    selected_tests = _select_representative_failures(failed_tests)
    error_pattern = _analyze_error_pattern(failed_tests)
    
    # Format failures for prompt
    failure_details = []
    simplest_case = selected_tests[0] if selected_tests else {}
    
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
    
    prompt = f"""You are a competitive programming debugging expert.

## Problem Description
{problem_desc}

## Selected Approach
Algorithm: {algorithm}
Steps:
{steps_text}

## Current Status
Iteration: {iteration}
Pass Rate: {pass_rate:.1%}
Error Pattern: {error_pattern}

## Current Code
```cpp
{code}
```

## Representative Failures
{failures_text}

## Debugging Task
1. **Trace Analysis**: Choose the Simplest Failure Case above. Mentally trace the code execution step-by-step with that input. Track key variables (e.g., loop counters, dp states, geometric coordinates, binary search bounds).
2. **Identify Deviation**: Explicitly state where the logic diverges from the correct path. Is the binary search range wrong? Is the geometry checking logic flawed? Is there an off-by-one error?
3. **Refine Approach**: output specific code fixes. If the current algorithm approach seems fundamentally flawed for these cases, suggest a corrected logic.

Provide your analysis and fixed code structure below.
"""
    
    analysis = llm.generate(prompt)
    
    return {
        'error_type': 'test_failure',
        'failed_count': len(failed_tests),
        'analysis': analysis,
        'error_pattern': error_pattern,
        'suggested_fixes': [], 
    }

