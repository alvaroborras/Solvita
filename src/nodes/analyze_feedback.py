"""Analyze Feedback Node - Analyze failures and provide improvement suggestions"""

from typing import Dict, Any
from loguru import logger
from src.graph.state import SolvitaState, FeedbackData
from src.llm import UnifiedLLMClient


def analyze_feedback_node(state: SolvitaState) -> Dict[str, Any]:
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
    
    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])
    
    # Analyze compilation errors first (higher priority)
    if compilation_errors:
        feedback_dict = _analyze_compilation_errors(llm, code, compilation_errors)
    else:
        # Analyze test failures
        failed_tests = [t for t in test_results if not t.get('passed', False)]
        feedback_dict = _analyze_test_failures(llm, code, failed_tests)
    
    feedback = FeedbackData(
        feedback=feedback_dict,
        suggested_fixes=feedback_dict.get('suggested_fixes', []),
    )
    
    return {
        "feedback": feedback,
        "execution_log": ["✓ Feedback analyzed"],
        "llm_calls": state['llm_calls'] + 1,
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


def _analyze_test_failures(llm: UnifiedLLMClient, code: str, failed_tests: list[Dict]) -> Dict:
    """Analyze test failures"""
    if not failed_tests:
        return {'error_type': 'none', 'analysis': 'No failures', 'suggested_fixes': []}
    
    # Summarize failures
    failure_summary = []
    for test in failed_tests[:5]:  # Limit to first 5 failures
        failure_summary.append(
            f"Input: {test.get('input', '')}\n"
            f"Expected: {test.get('expected', '')}\n"
            f"Actual: {test.get('actual', '')}\n"
            f"Error: {test.get('error', 'Wrong output')}"
        )
    
    failures_text = '\n\n'.join(failure_summary)
    
    prompt = f"""The following C++ code is producing wrong outputs:

Code:
```cpp
{code}
```

Failed Tests ({len(failed_tests)} total, showing first 5):
{failures_text}

Analyze why the code is failing and suggest specific fixes."""
    
    analysis = llm.generate(prompt)
    
    return {
        'error_type': 'test_failure',
        'failed_count': len(failed_tests),
        'analysis': analysis,
        'suggested_fixes': [],  # LLM provides fixes in analysis text
    }

