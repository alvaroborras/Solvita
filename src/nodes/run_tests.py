"""Run Tests Node - Execute tests against compiled code"""

from typing import Dict, Any
import subprocess
from loguru import logger
from src.graph.state import SolvitaState


def run_tests_node(state: SolvitaState) -> Dict[str, Any]:
    """
    Run test cases against compiled executable
    
    Returns:
    - test_results: list of results for each test
    - passed_tests: count of passed tests
    - pass_rate: percentage of tests passed
    """
    logger.info("[Node] Running tests")
    
    exe_path = state['solution'].get('executable_path')
    tests = state['tests'].get('generated_tests', [])
    
    if not exe_path:
        logger.debug("No executable path found (waiting for compilation)")
        # Don't modify tests field when no executable - just return empty update
        return {
            "execution_log": ["Waiting for compilation"],
        }
    
    results = []
    passed = 0
    
    for i, test in enumerate(tests):
        test_input = test.get('input', '')
        expected = test.get('expected_output', '').strip()
        
        try:
            # Run executable with test input
            result = subprocess.run(
                [exe_path],
                input=test_input,
                capture_output=True,
                text=True,
                timeout=2  # 2 second timeout per test
            )
            
            actual = result.stdout.strip()
            
            # Compare output
            passed_test = (actual == expected)
            if passed_test:
                passed += 1
            
            results.append({
                'test_id': i,
                'input': test_input,
                'expected': expected,
                'actual': actual,
                'passed': passed_test,
                'error': result.stderr if result.stderr else None,
            })
        
        except subprocess.TimeoutExpired:
            results.append({
                'test_id': i,
                'input': test_input,
                'expected': expected,
                'actual': '',
                'passed': False,
                'error': 'Timeout',
            })
        except Exception as e:
            results.append({
                'test_id': i,
                'input': test_input,
                'expected': expected,
                'actual': '',
                'passed': False,
                'error': str(e),
            })
    
    total = len(tests)
    pass_rate = passed / total if total > 0 else 0.0

    # Preserve existing test fields
    updated_tests = dict(state['tests'])
    updated_tests.update({
        "test_results": results,
        "passed_tests": passed,
        "pass_rate": pass_rate,
    })

    return {
        "tests": updated_tests,
        "execution_log": [f"Tests completed: {passed}/{total} passed ({pass_rate:.1%})"],
    }

