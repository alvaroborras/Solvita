"""Run Tests Node - Execute tests against compiled code"""

from typing import Dict, Any, TYPE_CHECKING
import subprocess
from loguru import logger

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


import tempfile
from pathlib import Path
from src.utils.cpp_execution import ExecutionLimits
from src.utils.output_judging import judge_output_against_certified_expected

def run_tests_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Run test cases against compiled executable
    
    Returns:
        test_results: list of results for each test
        passed_tests: count of passed tests
        pass_rate: percentage of tests passed
    """
    logger.info("[Node] Running tests")
    
    exe_path = state['solution'].get('executable_path')
    tests_data = state.get('tests', {})
    tests = tests_data.get('generated_tests', [])
    checker_exe = tests_data.get('checker_exe')
    
    if not exe_path:
        logger.debug("No executable path found (waiting for compilation)")
        updated_tests = dict(tests_data)
        updated_tests["pending_execution"] = True
        return {
            "tests": updated_tests,
            "execution_log": ["Waiting for compilation"],
        }

    if not tests:
        logger.debug("No tests found (waiting for test generation)")
        updated_tests = dict(tests_data)
        updated_tests["pending_execution"] = True
        return {
            "tests": updated_tests,
            "execution_log": ["Waiting for test generation"],
        }
    
    results = []
    passed = 0
    
    # Create a temp dir for test files (checker needs files)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for i, test in enumerate(tests):
            test_input = test.get('input', '')
            expected = test.get('expected_output', '').strip()
            
            try:
                # Run executable with test input (using ExecutionLimits)
                from src.utils.cpp_execution import run_program
                retcode, stdout, stderr = run_program(
                    Path(exe_path),
                    input_text=test_input,
                    limits=ExecutionLimits.default_run()
                )
                
                # Create result object for compatibility
                class Result:
                    def __init__(self, returncode, stdout, stderr):
                        self.returncode = returncode
                        self.stdout = stdout
                        self.stderr = stderr
                
                result = Result(retcode, stdout, stderr)
                
                actual = result.stdout.strip()
                passed_test = False
                error_msg = result.stderr if result.stderr else None

                input_file = tmp_path / f"input_{i}.txt"
                output_file = tmp_path / f"output_{i}.txt"
                answer_file = tmp_path / f"answer_{i}.txt"

                input_file.write_text(test_input, encoding="utf-8")
                output_file.write_text(result.stdout, encoding="utf-8")
                answer_file.write_text(expected, encoding="utf-8")

                passed_test, judge_msg = judge_output_against_certified_expected(
                    actual_output=result.stdout,
                    expected_output=expected,
                    checker_exe=Path(checker_exe) if checker_exe else None,
                    input_path=input_file,
                    output_path=output_file,
                    answer_path=answer_file,
                )
                if not passed_test and judge_msg:
                    error_msg = f"{error_msg or ''}\n{judge_msg}".strip()
                
                if passed_test:
                    passed += 1
                
                results.append({
                    'test_id': i,
                    'input': test_input,
                    'expected': expected,
                    'actual': actual,
                    'passed': passed_test,
                    'error': error_msg,
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
        "pending_execution": False,
    })

    return {
        "tests": updated_tests,
        "execution_log": [f"Tests completed: {passed}/{total} passed ({pass_rate:.1%})"],
    }
