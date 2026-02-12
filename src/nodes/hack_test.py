"""Hack Test Node - Adversarial testing for solutions"""

import json
from typing import Dict, Any, List, TYPE_CHECKING
from loguru import logger
from src.llm import UnifiedLLMClient

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

import tempfile
import subprocess
from pathlib import Path
from src.utils.cpp_execution import run_checker


def build_hacker_prompt(problem_desc: str, constraints: Dict[str, Any], code: str) -> str:
    return f"""You are a competitive programming hacker. Your goal is to find a test case that breaks the given solution.

Problem Description:
{problem_desc}

Constraints:
{json.dumps(constraints, indent=2)}

Solution Code:
```cpp
{code}
```

Task:
1. Analyze the code for potential bugs (e.g., overflow, edge cases, special graph structures, off-by-one errors).
2. Generate 1-5 specific test cases that might cause the solution to fail (Wrong Answer, Runtime Error, or TLE).
3. Do NOT generate random large inputs unless you have a specific reason (e.g. max value overflow). Focus on tricky logic.

Return ONLY a JSON object. No other text.
Schema:
{{
    "analysis": "<brief analysis of potential weak points>",
    "hack_tests": [
        {{"input": "<input string>", "expected_output": "<optional expected output or empty string>"}}
    ]
}}
"""


def hack_test_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Adversarial Hack Phase
    
    1. LLM analyzes code and generates "hack" test cases.
    2. Run these tests against the executable.
    3. Update state with hack results.
    """
    logger.info("[Node] Adversarial Hack")
    
    config = state.get("config", {}).copy()
    config["model"] = "claude-opus-4-6" # Use specific hacker model
    
    code = state["solution"].get("code", "")
    exe_path = state["solution"].get("executable_path")
    problem_desc = state["problem"].get("description", "")
    constraints = state["problem"].get("constraints", {})
    hack_round = state.get("hack_round", 0) + 1
    
    if not exe_path or not Path(exe_path).exists():
        logger.error("No executable found for hack test")
        return {"hack_passed": False, "hack_round": hack_round, "hack_failures": [{"error": "No executable"}]}

    # Initialize LLM
    llm = UnifiedLLMClient(config)
    
    # 1. Generate Hack Tests
    prompt = build_hacker_prompt(problem_desc, constraints, code)
    response = llm.generate(prompt)
    
    try:
        data = json.loads(response.strip().strip("```json").strip("```"))
        hack_tests = data.get("hack_tests", [])
        analysis = data.get("analysis", "No analysis")
        logger.info(f"Hacker Analysis: {analysis}")
        logger.info(f"Generated {len(hack_tests)} hack tests")
    except Exception as e:
        logger.warning(f"Failed to parse hacker response: {e}")
        return {
            "hack_round": hack_round,
            "hack_passed": True, # Skip this round if LLM fails, don't block
             "execution_log": [f"Hack round {hack_round} skipped (LLM parse error)"]
        }

    # 2. Run Hack Tests
    tests_data = state.get('tests', {})
    checker_exe = tests_data.get('checker_exe')
    
    failures = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for i, test in enumerate(hack_tests):
            inp = test.get("input", "")
            exp = test.get("expected_output", "").strip()
            
            try:
                # Run solution
                res = subprocess.run(
                    [exe_path],
                    input=inp,
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                actual = res.stdout.strip()
                
                if res.returncode != 0:
                    failures.append({
                        "type": "Runtime Error",
                        "input": inp,
                        "output": res.stderr,
                        "expected": exp
                    })
                    continue
                
                # Check correctness
                passed = False
                if checker_exe and Path(checker_exe).exists():
                    # Use specialized checker
                    input_file = tmp_path / f"hack_{i}.in"
                    output_file = tmp_path / f"hack_{i}.out"
                    answer_file = tmp_path / f"hack_{i}.ans"
                    
                    input_file.write_text(inp, encoding="utf-8")
                    output_file.write_text(res.stdout, encoding="utf-8") # raw stdout
                    
                    # If expected output is provided, use it. Otherwise use empty.
                    # Some checkers might crash with empty answer file but most require *something*.
                    # Hacker is instructed to provide expected_output if possible.
                    answer_file.write_text(exp if exp else "", encoding="utf-8")
                    
                    chk_ok, chk_msg = run_checker(Path(checker_exe), input_file, output_file, answer_file)
                    if not chk_ok:
                         failures.append({
                            "type": "Wrong Answer (Checker)",
                            "input": inp,
                            "output": actual,
                            "expected": exp,
                            "details": chk_msg
                        })
                else:
                    # Fallback string compare
                    # If no expected output provided, we assume PASS unless Runtime Error
                    if exp and actual != exp:
                        failures.append({
                            "type": "Wrong Answer",
                            "input": inp,
                            "output": actual,
                            "expected": exp
                        })
            
            except subprocess.TimeoutExpired:
                failures.append({
                    "type": "Time Limit Exceeded",
                    "input": inp,
                    "expected": exp
                })
            except Exception as e:
                 failures.append({
                    "type": "System Error",
                    "input": inp,
                    "details": str(e)
                })

    # Append new hack tests to generated_tests for regression testing
    generated_tests = tests_data.get('generated_tests', [])
    new_tests = []
    
    # Only add tests that have input strings
    for t in hack_tests:
        if t.get("input"):
            new_tests.append({
                "input": t.get("input"),
                "expected_output": t.get("expected_output", ""),
                "type": "hack"
            })
            
    updated_tests = dict(tests_data)
    updated_tests['generated_tests'] = generated_tests + new_tests
    updated_tests['total_tests'] = len(updated_tests['generated_tests'])

    if failures:
        logger.warning(f"Hack successful! Found {len(failures)} failures.")
        return {
            "hack_round": hack_round,
            "hack_passed": False,
            "hack_failures": failures,
            "tests": updated_tests, # Persist new tests
            "execution_log": [f"Hack round {hack_round} FAILED. Added {len(new_tests)} regression tests."]
        }
    
    logger.info(f"Hack round {hack_round} passed.")
    return {
        "hack_round": hack_round,
        "hack_passed": True,
        "hack_failures": [],
        "tests": updated_tests, # Persist new tests (even if passed, good for regression)
        "execution_log": [f"Hack round {hack_round} passed. Added {len(new_tests)} regression tests."]
    }
