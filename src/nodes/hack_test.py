"""Hack Test Node - Adversarial testing for solutions"""

import json
from typing import Dict, Any, List, TYPE_CHECKING
from loguru import logger
from src.llm import UnifiedLLMClient
from src.utils.json_utils import parse_json_response
from src.utils.problem_utils import extract_problem_code

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

import tempfile
import subprocess
from pathlib import Path
from src.utils.cpp_execution import run_checker, run_program, ExecutionLimits


def build_hacker_prompt(problem_desc: str, constraints: Dict[str, Any], code: str) -> str:
    constraints_json = json.dumps(constraints, indent=2)
    return f"""You are a competitive programming hacker. Your goal is to find a test case that breaks the given solution.

Problem Description:
{problem_desc}

⚠️ CONSTRAINTS (EVERY test input MUST satisfy ALL of these):
{constraints_json}

CRITICAL: If any value in your test input violates these constraints, the validator will reject it.
Focus on finding bugs WITHIN the constraint bounds, not by exceeding them.

Solution Code:
```cpp
{code}
```

ANALYSIS TASK:
1. Identify specific algorithmic bugs in the code (overflow, edge cases, boundary conditions, wrong logic paths).
2. Generate 1-5 test inputs that trigger these bugs WHILE RESPECTING ALL CONSTRAINTS.
3. For boundary cases, use values at or near the constraint limits if possible.
4. Every single value must be within the specified ranges.

INPUT FORMAT (MUST FOLLOW EXACTLY):
Each line must end with exactly one newline character.
Do not add extra blank lines.

Return ONLY valid JSON with no other text.

VALID JSON Schema:
{{
    "analysis": "<identification of bugs found in the code>",
    "hack_tests": [
        {{"input": "<complete input string including all newlines, respecting all constraints>"}}
    ]
}}

Example response (if n <= 5, k <= 3):
{{
    "analysis": "Bug: when n=2 and values are similar, the algorithm fails to handle the case correctly",
    "hack_tests": [
        {{"input": "2 1\\n1000000000 0\\n-1000000000 0\\n"}}
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
    def normalize_hack_input(inp: str) -> str:
        """
        Normalize hack test input to ensure it matches validator requirements.
        """
        lines = inp.split('\n')
        normalized_lines = []
        
        for line in lines:
            if line.strip() == "":
                continue
            normalized_lines.append(line.rstrip())
        
        if normalized_lines:
            return '\n'.join(normalized_lines) + '\n'
        return inp
    
    logger.info("[Node] Adversarial Hack")
    
    config = UnifiedLLMClient.build_role_config(state.get("config", {}), "hacker")
    
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
        data = parse_json_response(response)
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
    validator_exe = tests_data.get('validator_exe')
    
    failures = []
    validator_rejected_count = 0
    validated_hacks = []  # Track only hacks that passed validator
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for i, test in enumerate(hack_tests):
            inp = test.get("input", "")
            exp = test.get("expected_output", "").strip()
            
            # Normalize input to ensure proper formatting
            inp = normalize_hack_input(inp)

            if validator_exe and Path(validator_exe).exists():
                v_code, _, v_err = run_program(
                    Path(validator_exe),
                    input_text=inp,
                    limits=ExecutionLimits.default_run(),
                )
                if v_code != 0:
                    validator_rejected_count += 1
                    logger.debug(f"[HACK] Validator rejected input {i}: {v_err}")
                    logger.debug(f"[HACK] Input was: {repr(inp[:100])}")
                    continue
            
            # Passed validator (or no validator exists) - mark as valid for regression
            validated_hacks.append({"input": inp, "expected_output": exp})

            
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
    # ONLY add tests that passed the validator
    generated_tests = tests_data.get('generated_tests', [])
    new_tests = []
    
    # Only add tests that have input strings and passed validator
    for t in validated_hacks:
        if t.get("input"):
            new_tests.append({
                "input": t.get("input"),
                "expected_output": t.get("expected_output", ""),
                "type": "hack"
            })
            
    updated_tests = dict(tests_data)
    updated_tests['generated_tests'] = generated_tests + new_tests
    updated_tests['total_tests'] = len(updated_tests['generated_tests'])

    # Persist hack tests to disk in the same format/location as other tests
    problem_code = extract_problem_code(state.get("raw_problem", {}))
    if problem_code:
        tests_dir = Path("data") / "generated" / problem_code / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        existing = list(tests_dir.glob("hack_*.in"))
        next_idx = 0
        if existing:
            try:
                indices = [int(p.stem.split("_")[1]) for p in existing if p.stem.count("_") == 1]
                next_idx = max(indices) + 1 if indices else 0
            except ValueError:
                next_idx = 0

        for offset, t in enumerate(new_tests):
            inp = t.get("input", "")
            exp = t.get("expected_output", "")
            input_path = tests_dir / f"hack_{next_idx + offset}.in"
            output_path = tests_dir / f"hack_{next_idx + offset}.out"
            input_path.write_text(inp.rstrip("\n") + "\n", encoding="utf-8")
            output_path.write_text(exp.rstrip("\n") + ("\n" if exp else ""), encoding="utf-8")

    if failures:
        logger.warning(f"Hack successful! Found {len(failures)} failures.")
        if validator_rejected_count > 0:
            logger.warning(f"Note: {validator_rejected_count} hack tests were rejected by validator (format errors)")
        return {
            "hack_round": hack_round,
            "hack_passed": False,
            "hack_failures": failures,
            "tests": updated_tests, # Persist new tests
            "execution_log": [f"Hack round {hack_round} FAILED. Added {len(new_tests)} regression tests."]
        }
    
    logger.info(f"Hack round {hack_round} passed.")
    if validator_rejected_count > 0:
        logger.warning(f"Note: {validator_rejected_count} hack tests were rejected by validator (format errors)")
    return {
        "hack_round": hack_round,
        "hack_passed": True,
        "hack_failures": [],
        "tests": updated_tests, # Persist new tests (even if passed, good for regression)
        "execution_log": [f"Hack round {hack_round} passed. Added {len(new_tests)} regression tests. ({validator_rejected_count} inputs rejected by validator)"]
    }
