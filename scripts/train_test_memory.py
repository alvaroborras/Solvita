"""
Offline training script for the test generation memory policy.

Usage:
    python scripts/train_test_memory.py \
        --data data/solvita_train/solvita_train_tanh.jsonl \
        --limit 500 \
        --max-tests 50

Workflow per problem:
  1. Load problem & correct_solution from JSONL.
  2. Generate test cases using `generate_tests_node` (which queries the test memory and logs the item IDs).
  3. Compile/Prepare the oracle executable from `correct_solution` using `prepare_executable`.
  4. Run the generated tests on the oracle solution using `run_tests_node`.
  5. Compute the inverted reward (pass_rate logic) and settle updates using `update_test_memory_node`.
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

from src.graph.state import create_initial_state
from src.nodes.generate_tests import generate_tests_node
from src.nodes.compile_code import prepare_executable
from src.nodes.run_tests import run_tests_node
from src.nodes.update_test_memory import update_test_memory_node
from src.utils.cpp_execution import ExecutionLimits

logger.remove()
logger.add(lambda msg: tqdm.write(msg, end=""), level="INFO")

def pick_oracle(solutions: list) -> dict:
    """Pick the first C++ solution if available, otherwise Python. Use heuristic if language missing."""
    if not solutions:
        return None
        
    for sol in solutions:
        lang = sol.get("language", "").lower()
        if "c++" in lang or "cpp" in lang:
            return sol
            
    # Fallback to the first one, but guess language if missing
    fallback = solutions[0]
    if not fallback.get("language"):
        code = fallback.get("code", "")
        # Heuristic: C++ usually has #include
        if "#include" in code or "using namespace" in code:
            fallback["language"] = "C++"
        else:
            fallback["language"] = "Python 3"
            
    return fallback

def train_one(record: dict, config: dict, tmp_base: Path) -> dict:
    """Process a single training problem."""
    # 1. Create initial state
    raw_problem = {
        "description": record.get("description", ""),
        "time_limit": record.get("time_limit", 2000),
        "space_limit": record.get("space_limit", 256),
        "public_tests": [{"input": pt.get("input", ""), "output": pt.get("output", "")} 
                         for pt in record.get("public_tests", [])],
        "_metadata": {
            "problem_id": record.get("id", "unknown")
        }
    }
    
    state = create_initial_state(raw_problem, config)
    
    canonical = record.get("canonical", {})
    if not canonical and "problem_type" in record:
        canonical["problem_type"] = [record["problem_type"]]
        
    state["problem"]["canonical"] = canonical
    
    # Needs a config for the LLM graph
    state["config"] = config
    
    # 2. Generate test cases
    logger.info(f"Generating tests for {record.get('id', 'unknown')}...")
    gen_result = generate_tests_node(state)
    state = {**state, **gen_result}
    
    if not state.get("tests", {}).get("generated_tests"):
        return {"skipped": True, "reason": "no_tests"}

    # 3. Compile/Prepare the standard solution (oracle)
    solutions = record.get("correct_solution", [])
    if isinstance(solutions, str):
        try:
            solutions = ast.literal_eval(solutions)
        except Exception:
            solutions = [{"code": solutions, "language": "C++"}] # fallback
            
    oracle = pick_oracle(solutions)
    if not oracle:
        return {"skipped": True, "reason": "no_oracle"}

    logger.info(f"Preparing oracle executable for {record.get('id', 'unknown')} ({oracle.get('language', 'unknown')})...")
    tmp_dir = Path(tempfile.mkdtemp(dir=tmp_base, prefix="oracle_"))
    
    exe_path, errors = prepare_executable(
        oracle.get("code", ""), 
        oracle.get("language", "C++"), 
        tmp_dir, 
        diagnostic=False,
        limits=ExecutionLimits.default_compile()
    )
    
    if not exe_path:
        return {"skipped": True, "reason": f"compile_fail_oracle: {errors}"}
        
    state["solution"]["executable_path"] = str(exe_path)

    # 3.5 Compile/Prepare the buggy solution (incorrect)
    buggy_solutions = record.get("incorrect_solution", [])
    if isinstance(buggy_solutions, str):
        try:
            buggy_solutions = ast.literal_eval(buggy_solutions)
        except Exception:
            buggy_solutions = [{"code": buggy_solutions, "language": "C++"}] # fallback
            
    buggy = pick_oracle(buggy_solutions) # pick the first usable one
    buggy_exe_path = None
    if buggy:
        logger.info(f"Preparing buggy executable for {record.get('id', 'unknown')} ({buggy.get('language', 'unknown')})...")
        buggy_tmp_dir = Path(tempfile.mkdtemp(dir=tmp_base, prefix="buggy_"))
        buggy_exe_path, buggy_errors = prepare_executable(
            buggy.get("code", ""), 
            buggy.get("language", "C++"), 
            buggy_tmp_dir, 
            diagnostic=False,
            limits=ExecutionLimits.default_compile()
        )
        if not buggy_exe_path:
            logger.warning(f"Failed to compile buggy solution: {buggy_errors}")

    # 4. Run tests on Oracle
    logger.info(f"Running tests on oracle for {record.get('id', 'unknown')}...")
    run_result = run_tests_node(state)
    state = {**state, **run_result}
    pass_rate_oracle = state.get("tests", {}).get("pass_rate", 0.0)

    # 4.5 Run tests on Buggy
    pass_rate_buggy = 1.0 # default to passing everything if no buggy solution
    if buggy_exe_path:
        logger.info(f"Running tests on buggy solution for {record.get('id', 'unknown')}...")
        # temporarily swap the executable path
        state["solution"]["executable_path"] = str(buggy_exe_path)
        buggy_run_result = run_tests_node(state)
        pass_rate_buggy = buggy_run_result.get("tests", {}).get("pass_rate", 0.0)
        # restore oracle executable path just in case
        state["solution"]["executable_path"] = str(exe_path)
    else:
        logger.info(f"No valid buggy solution compiled, skipping buggy evaluation.")

    # 5. Reward calculation and memory settlement
    # IMPORTANT PRINCIPLE: 
    # 1. Oracle must PASS (pass_rate_oracle -> 1.0) because it's correct.
    # 2. Buggy must FAIL (pass_rate_buggy -> 0.0) because it's incorrect.
    # We want tests that are valid (Oracle passes) AND hard/discriminating (Buggy fails).
    # If we couldn't compile a buggy solution, we fall back to just the oracle reward.
    
    if buggy_exe_path:
        # Dual Reward
        dual_score = pass_rate_oracle * (1.0 - pass_rate_buggy)
        reward = dual_score * 2.0 - 1.0
        logger.info(f"Problem {record.get('id', 'unknown')} finished. Oracle Pass: {pass_rate_oracle:.1%}, Buggy Pass: {pass_rate_buggy:.1%}, Reward: {reward:+.2f}")
    else:
        # Fallback Single Reward
        reward = pass_rate_oracle * 2.0 - 1.0
        logger.info(f"Problem {record.get('id', 'unknown')} finished. Oracle Pass: {pass_rate_oracle:.1%}, (No Buggy), Reward: {reward:+.2f}")

    # Settle memory (store the dual score as the final metric)
    state["tests"]["pass_rate"] = pass_rate_oracle * (1.0 - pass_rate_buggy) if buggy_exe_path else pass_rate_oracle
    update_test_memory_node(state)

    return {
        "pass_rate_oracle": pass_rate_oracle, 
        "pass_rate_buggy": pass_rate_buggy,
        "reward": reward, 
        "generated_tests": len(state.get("tests", {}).get("generated_tests", []))
    }

def main():
    parser = argparse.ArgumentParser(description="Train Test Memory Policy")
    parser.add_argument("--data", type=str, required=True, help="Path to JSONL data file")
    parser.add_argument("--limit", type=int, default=0, help="Max problems to process (0 = all)")
    parser.add_argument("--max-tests", type=int, default=10, help="Max tests to generate per problem")
    parser.add_argument("--epsilon", type=float, default=0.3, help="Exploration rate during training")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent workers")
    args = parser.parse_args()

    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": "data/memory",
            "test_top_k": 3,
            "test_epsilon": args.epsilon,
        },
        "max_tests": args.max_tests,
        "llm_model": "gemini-2.5-pro", # Use standard model for generation
    }

    # Load data
    records = []
    with open(args.data, "r") as f:
        for line in f:
            if not line.strip(): continue
            records.append(json.loads(line))
            
    if args.limit > 0:
        records = records[:args.limit]

    logger.info(f"Starting training on {len(records)} problems...")
    
    stats = {"success": 0, "skipped": 0, "total_tests": 0, "avg_reward": 0.0}
    reward_sum = 0.0

    tmp_base = Path(tempfile.mkdtemp(prefix="solvita_train_"))
    
    import concurrent.futures
    import threading
    stats_lock = threading.Lock()

    def _process_one(args_tuple):
        i, record = args_tuple
        try:
            res = train_one(record, config, tmp_base)
            with stats_lock:
                if res.get("skipped"):
                    stats["skipped"] += 1
                    logger.warning(f"Skipped problem {i}: {res.get('reason')}")
                else:
                    stats["success"] += 1
                    stats["total_tests"] += res.get("generated_tests", 0)
                    reward_sum_incr = res.get("reward", 0.0)
                    # use a global or dictionary reference for reward_sum
                    # since reward_sum is a local float we need a mutable object
                    return res, i
        except Exception as e:
            logger.error(f"Error processing problem {i}: {e}")
            with stats_lock:
                stats["skipped"] += 1
        return None, i

    try:
        futures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            # We wrap with list() and tqdm to show progress as jobs complete
            for _res, _i in tqdm(
                executor.map(_process_one, enumerate(records)),
                total=len(records), 
                desc="Training (Parallel)"
            ):
                if _res:
                    reward_sum += _res.get("reward", 0.0)
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)
        
    if stats["success"] > 0:
        stats["avg_reward"] = reward_sum / stats["success"]
        
    logger.info(f"Training complete. Stats: {stats}")

if __name__ == "__main__":
    main()
