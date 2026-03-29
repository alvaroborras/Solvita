"""
Offline training script for the Hacker Input Generation policy.

Legacy auxiliary script for experimental hacker-input evaluation.

Do not use this script as the formal Hacker memory trainer.
The official trainer entrypoint is `scripts/train_hacker.py`.

Usage:
    python scripts/train_hacker_input.py \\
        --data data/solvita_train/solvita_train_tanh.jsonl \\
        --limit 500

Workflow per problem:
  1. Load problem & correct_solution (Oracle) & incorrect_solution (Buggy) from JSONL.
  2. If no Buggy solution exists, skip.
  3. Compile Oracle and Buggy.
  4. Run `hack_test_node` passing the Buggy executable.
  5. The Hacker LLM attempts to generate inputs to break the Buggy code.
  6. Generated inputs are tested against Oracle.
  7. Compute Reward = pass_rate_oracle * (1.0 - pass_rate_buggy)
  8. Update Hacker Input Memory (to be implemented)
"""

import argparse
import ast
import json
import os
import shutil
import tempfile
from pathlib import Path
from tqdm import tqdm
from loguru import logger
import threading
import concurrent.futures

from src.graph.state import create_initial_state
from src.nodes.hack_test import hack_test_node
from src.nodes.compile_code import prepare_executable
from src.nodes.run_tests import run_tests_node
from src.nodes.update_hacker_memory import update_hacker_memory_node
from src.utils.cpp_execution import ExecutionLimits, run_program

logger.remove()
logger.add(lambda msg: tqdm.write(msg, end=""), level="INFO")

def pick_oracle(solutions: list) -> dict:
    """Pick the first C++ solution if available, otherwise Python."""
    if not solutions:
        return None
        
    for sol in solutions:
        lang = sol.get("language", "").lower()
        if "c++" in lang or "cpp" in lang:
            return sol
            
    fallback = solutions[0]
    if not fallback.get("language"):
        code = fallback.get("code", "")
        if "#include" in code or "using namespace" in code:
            fallback["language"] = "C++"
        else:
            fallback["language"] = "Python 3"
            
    return fallback

def train_one(record: dict, config: dict, tmp_base: Path) -> dict:
    """Process a single training problem for Hacker Input."""
    raw_problem = {
        "description": record.get("description", ""),
        "time_limit": record.get("time_limit", 2000),
        "space_limit": record.get("space_limit", 256),
        "public_tests": [{"input": pt.get("input", ""), "output": pt.get("output", "")} 
                         for pt in record.get("public_tests", [])],
        "_metadata": {"problem_id": record.get("id", "unknown")},
        "constraints": record.get("constraints", {})
    }
    
    state = create_initial_state(raw_problem, config)
    state["config"] = config
    
    # Needs to start with empty tests list so we only evaluate hacker outputs
    state["tests"] = {"generated_tests": [], "total_tests": 0}

    # Extract target solutions
    solutions = record.get("correct_solution", [])
    if isinstance(solutions, str):
        try: solutions = ast.literal_eval(solutions)
        except: solutions = [{"code": solutions, "language": "C++"}]
    oracle = pick_oracle(solutions)

    buggy_solutions = record.get("incorrect_solution", [])
    if isinstance(buggy_solutions, str):
        try: buggy_solutions = ast.literal_eval(buggy_solutions)
        except: buggy_solutions = [{"code": buggy_solutions, "language": "C++"}]
    buggy = pick_oracle(buggy_solutions)

    if not buggy:
        return {"skipped": True, "reason": "no_buggy_solution"}
    if not oracle:
        return {"skipped": True, "reason": "no_oracle_solution"}

    # Compile files
    oracle_tmp = Path(tempfile.mkdtemp(dir=tmp_base, prefix="oracle_"))
    buggy_tmp = Path(tempfile.mkdtemp(dir=tmp_base, prefix="buggy_"))

    logger.info(f"[{record.get('id', 'unknown')}] Compiling Oracle ({oracle.get('language')}) and Buggy ({buggy.get('language')})")
    oracle_exe, o_err = prepare_executable(oracle.get("code", ""), oracle.get("language", "C++"), oracle_tmp, limits=ExecutionLimits.default_compile())
    buggy_exe, b_err = prepare_executable(buggy.get("code", ""), buggy.get("language", "C++"), buggy_tmp, limits=ExecutionLimits.default_compile())

    if not oracle_exe:
        return {"skipped": True, "reason": f"oracle_compile_fail: {o_err}"}
    if not buggy_exe:
        return {"skipped": True, "reason": f"buggy_compile_fail: {b_err}"}

    # Setup state for Hacker. Hacker attacks the `state["solution"]`.
    state["solution"] = {
        "code": buggy.get("code", ""),
        "executable_path": str(buggy_exe)
    }

    # 1. Run the Hacker node
    logger.info(f"[{record.get('id', 'unknown')}] Running Hacker Model against Buggy code...")
    hack_result = hack_test_node(state)
    state = {**state, **hack_result}

    # Calculate Buggy pass rate on Hacker Tests. 
    # hack_test_node filters invalid format inputs, only tries valid ones.
    generated_hack_tests = state.get("tests", {}).get("generated_tests", [])
    if not generated_hack_tests:
        return {"skipped": True, "reason": "hacker_generated_no_valid_inputs"}

    # 2. Run Oracle to establish Ground Truth
    logger.info(f"[{record.get('id', 'unknown')}] Running Oracle to establish ground truth...")
    valid_tests = []
    oracle_crashes = 0
    for t in generated_hack_tests:
        inp = t.get("input", "")
        # Run oracle with strict limits
        o_code, o_out, o_err = run_program(oracle_exe, input_text=inp, limits=ExecutionLimits.default_run())
        if o_code == 0:
            # Overwrite the Hacker LLM's guessed output with the TRUE Ground Truth from Oracle!
            t["expected_output"] = o_out.strip() + "\n"
            valid_tests.append(t)
        else:
            oracle_crashes += 1

    if not valid_tests:
        return {"skipped": True, "reason": "oracle_crashed_on_all_hacker_inputs"}

    pass_rate_oracle = len(valid_tests) / len(generated_hack_tests)

    # Put only the perfectly valid tests back into state
    state["tests"]["generated_tests"] = valid_tests
    state["tests"]["total_tests"] = len(valid_tests)

    # 3. Verify inputs against Buggy using standard checker flow
    logger.info(f"[{record.get('id', 'unknown')}] Running Buggy against {len(valid_tests)} Ground-Truth inputs...")
    state["solution"]["executable_path"] = str(buggy_exe)
    # Using run_tests_node allows checking with testlib checkers if they exist, 
    # ensuring perfect verification against the newly generated Ground Truth!
    buggy_result = run_tests_node(state)
    state = {**state, **buggy_result}
    
    pass_rate_buggy = state.get("tests", {}).get("pass_rate", 0.0)

    # 4. Calculate Reward
    # Reward is high if Oracle passes (legitimate input format) AND Buggy fails
    reward = pass_rate_oracle * (1.0 - pass_rate_buggy) * 2.0 - 1.0
    state["hacker_reward"] = reward

    logger.info(f"[{record.get('id', 'unknown')}] Finished! Oracle Pass: {pass_rate_oracle*100:.1f}%, Buggy Fail: {(1.0-pass_rate_buggy)*100:.1f}%, Reward: {reward:+.2f}")

    # Settle memory
    update_hacker_memory_node(state)

    return {
        "reward": reward,
        "pass_rate_oracle": pass_rate_oracle,
        "pass_rate_buggy": pass_rate_buggy,
        "generated_tests": len(valid_tests)
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    config = {
        "llm_model": "gemini-2.5-pro",
    }

    records = []
    with open(args.data, "r") as f:
        for line in f:
            if not line.strip(): continue
            records.append(json.loads(line))
            
    if args.limit > 0:
        records = records[:args.limit]

    logger.info(f"Starting Hacker Input Training on {len(records)} problems...")
    
    stats = {"success": 0, "skipped": 0, "total_tests": 0}
    reward_sum = 0.0
    tmp_base = Path(tempfile.mkdtemp(prefix="solvita_hacker_"))
    stats_lock = threading.Lock()

    def _process_one(args_tuple):
        i, record = args_tuple
        try:
            res = train_one(record, config, tmp_base)
            with stats_lock:
                if res.get("skipped"):
                    stats["skipped"] += 1
                    logger.warning(f"Skipped {i}: {res.get('reason')}")
                else:
                    stats["success"] += 1
                    stats["total_tests"] += res.get("generated_tests", 0)
                    return res, i
        except Exception as e:
            logger.error(f"Error {i}: {e}")
            with stats_lock:
                stats["skipped"] += 1
        return None, i

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for _res, _i in tqdm(
            executor.map(_process_one, enumerate(records)),
            total=len(records), 
            desc="Training Hacker"
        ):
            if _res:
                reward_sum += _res.get("reward", 0.0)

    try:
        shutil.rmtree(tmp_base)
    except:
        pass

    logger.info("=" * 40)
    logger.info("HACKER TRAINING RUN COMPLETE")
    logger.info(f"Processed: {stats['success']} successful, {stats['skipped']} skipped")
    logger.info(f"Total Inputs Generated: {stats['total_tests']}")
    if stats["success"] > 0:
        logger.info(f"Average Reward: {reward_sum / stats['success']:+.3f}")

if __name__ == "__main__":
    main()
