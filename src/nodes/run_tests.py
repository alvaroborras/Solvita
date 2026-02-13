"""Run Tests Node - Execute tests against compiled code"""

from typing import Dict, Any, TYPE_CHECKING
import subprocess
from loguru import logger

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


import tempfile
from pathlib import Path
from src.utils.cpp_execution import run_checker, ExecutionLimits

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
        return {
            "execution_log": ["Waiting for compilation"],
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

                if checker_exe and Path(checker_exe).exists():
                    # Use Special Checker
                    input_file = tmp_path / f"input_{i}.txt"
                    output_file = tmp_path / f"output_{i}.txt"
                    answer_file = tmp_path / f"answer_{i}.txt"
                    
                    input_file.write_text(test_input, encoding="utf-8")
                    output_file.write_text(result.stdout, encoding="utf-8") # Use raw stdout for checker
                    answer_file.write_text(expected, encoding="utf-8")
                    
                    chk_ok, chk_msg = run_checker(Path(checker_exe), input_file, output_file, answer_file)
                    passed_test = chk_ok
                    if not passed_test:
                        # Append checker message to error
                        error_msg = f"{error_msg or ''}\nChecker: {chk_msg}".strip()
                else:
                    # Fallback to string equality
                    passed_test = (actual == expected)
                
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
    })

    return {
        "tests": updated_tests,
        "execution_log": [f"Tests completed: {passed}/{total} passed ({pass_rate:.1%})"],
    }

