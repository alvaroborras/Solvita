"""
Investigation script to run a specific problem from the dataset and trace the 
results of the oracle to identify why it scored a 0.0% pass rate.
"""

import argparse
import ast
import json
import os
import shutil
import tempfile
from pathlib import Path
from loguru import logger

from src.graph.state import create_initial_state
from src.nodes.generate_tests import generate_tests_node
from src.nodes.compile_code import prepare_executable
from src.nodes.run_tests import run_tests_node
from src.utils.cpp_execution import ExecutionLimits, run_program

def get_problem(data_file: str, prob_id: str) -> dict:
    with open(data_file, "r") as f:
        for line in f:
            if not line.strip(): continue
            rec = json.loads(line)
            if rec.get("id") == prob_id:
                return rec
    return None

def investigate(data_file: str, prob_id: str):
    logger.info(f"Looking for {prob_id}...")
    record = get_problem(data_file, prob_id)
    if not record:
        logger.error(f"Problem {prob_id} not found.")
        return
        
    logger.info(f"Found problem {prob_id}.")
    logger.info(f"Description:\n{record.get('description', '')[:500]}...\n")
    logger.info(f"Constraints: {record.get('constraints')}")
    
    # 1. State Setup
    config = {
        "trainable_memory": {"enabled": False}, # Disable memory to not pollute it
        "max_tests": 5, # Generate a small sample
        "generate_tests_target_count": 5, 
        "llm_model": "gemini-2.5-pro",
    }
    raw_problem = {
        "description": record.get("description", ""),
        "time_limit": record.get("time_limit", 2000),
        "space_limit": record.get("space_limit", 256),
        "public_tests": [{"input": pt.get("input", ""), "output": pt.get("output", "")} 
                         for pt in record.get("public_tests", [])],
        "_metadata": {"problem_id": f"investigate_{prob_id}"}
    }
    state = create_initial_state(raw_problem, config)
    state["config"] = config
    
    # 2. Generator
    logger.info(f"Generating tests...")
    gen_result = generate_tests_node(state)
    state = {**state, **gen_result}
    tests = state.get("tests", {}).get("generated_tests", [])
    logger.info(f"Generated {len(tests)} tests.")
    
    if not tests:
        logger.error("Failed to generate tests.")
        return
        
    # 3. Compile Oracle
    logger.info("Extracting and compiling Oracle...")
    solutions = record.get("correct_solution", [])
    if isinstance(solutions, str):
        try:
            solutions = ast.literal_eval(solutions)
        except:
            solutions = [{"code": solutions, "language": "C++"}] # fallback
            
    # Print the Oracle code being tested
    oracle = None
    for sol in solutions:
        lang = sol.get("language", "").lower()
        if "c++" in lang or "cpp" in lang:
            oracle = sol
            break
    if not oracle: oracle = solutions[0]
    
    logger.info(f"Oracle Language: {oracle.get('language')}")
    # print head and tail of code
    code = oracle.get('code', '')
    logger.info(f"Oracle Code (first 300 chars):\n{code[:300]}")
    
    tmp_dir = Path(tempfile.mkdtemp(prefix="investigate_oracle_"))
    try:
        exe_path, errors = prepare_executable(
            code, oracle.get("language", "C++"), tmp_dir, 
            diagnostic=False, limits=ExecutionLimits.default_compile()
        )
        if not exe_path:
            logger.error(f"Oracle compilation failed: {errors}")
            return
            
        logger.info("Oracle compiled successfully. Testing...")
        state["solution"]["executable_path"] = str(exe_path)
        
        # 4. We will run tests manually to get granular output
        checker_exe = state["tests"].get("checker_exe")
        for i, t in enumerate(tests):
            inp = t.get("input")
            expected = t.get("expected_output", "")
            logger.info(f"\n--- Test {i+1} ---")
            logger.info(f"Input: {inp.strip() if len(inp) < 100 else inp.strip()[:100]+'...'}")
            logger.info(f"Expected: {expected.strip() if len(expected) < 100 else expected.strip()[:100]+'...'}")
            
            code, out, err = run_program(exe_path, input_text=inp, limits=ExecutionLimits.default_run())
            
            logger.info(f"Oracle Return Code: {code}")
            logger.info(f"Oracle Stderr: {err.strip() if err else 'None'}")
            logger.info(f"Oracle Stdout: {out.strip() if len(out) < 100 else out.strip()[:100]+'...'}")
            
            passed = (out.strip() == expected.strip())
            logger.info(f"Passed text match: {passed}")
            
            if checker_exe and Path(checker_exe).exists():
                from src.utils.cpp_execution import run_checker
                in_f = tmp_dir / f"in_{i}.txt"
                out_f = tmp_dir / f"out_{i}.txt"
                ans_f = tmp_dir / f"ans_{i}.txt"
                in_f.write_text(inp, encoding="utf-8")
                out_f.write_text(out, encoding="utf-8")
                ans_f.write_text(expected, encoding="utf-8")
                
                chk_ok, chk_msg = run_checker(Path(checker_exe), in_f, out_f, ans_f)
                logger.info(f"Checker passed: {chk_ok}")
                logger.info(f"Checker msg: {chk_msg}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
         
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--prob", required=True)
    args = parser.parse_args()
    investigate(args.data, args.prob)
