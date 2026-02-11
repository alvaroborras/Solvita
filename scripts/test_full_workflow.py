"""
全流程端到端测试脚本
支持三种模式：
1. --workflow: 直接调用 LangGraph 的 run_workflow()
2. --step: 手动逐节点串联执行，方便调试
3. --quick: 跳过 generate_tests，使用 public tests 快速验证后半链路

用法:
    python -m scripts.test_full_workflow data/problems/livecodebench_1873_A.json --quick
    python -m scripts.test_full_workflow data/problems/livecodebench_1873_A.json --step
    python -m scripts.test_full_workflow data/problems/livecodebench_1873_A.json --workflow
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set TMPDIR to project-local tmp to avoid permission issues in restricted environments (e.g. sandboxes)
LOCAL_TMP = PROJECT_ROOT / "tmp"
LOCAL_TMP.mkdir(exist_ok=True)
os.environ["TMPDIR"] = str(LOCAL_TMP)

import argparse
import json
import time
from loguru import logger
from pprint import pprint

from src.graph.state import create_initial_state, merge_dict
from src.graph.workflow import run_workflow
from src.nodes import (
    retrieve_knowledge_node,
    plan_solution_node,
    generate_tests_node,
    generate_code_node,
    compile_code_node,
    run_tests_node,
    unified_check_node,
    analyze_feedback_node,
    status_routing,
    compilation_routing
)

def load_problem(path: str) -> dict:
    """Load problem JSON"""
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        logger.error(f"Problem file not found: {p}")
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def manual_merge_state(state: dict, update: dict) -> dict:
    """Simulate LangGraph state merging"""
    from operator import add as op_add

    reducers = {
        "problem": merge_dict,
        "plan": merge_dict,
        "solution": merge_dict,
        "tests": merge_dict,
        "feedback": merge_dict,
        "execution_log": op_add,
        "messages": op_add,
    }

    new_state = dict(state)
    for key, val in update.items():
        if key in reducers:
            # Handle list vs dict for merge_dict if needed, but usually merge_dict handles None
            curr = new_state.get(key)
            if key in ("execution_log", "messages") and curr is None:
                curr = []
            elif curr is None:
                curr = {}
            new_state[key] = reducers[key](curr, val)
        elif key == "llm_calls":
            # annotated[int, add]
            new_state[key] = new_state.get(key, 0) + val
        else:
            # default: overwrite
            new_state[key] = val
            
    return new_state

def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_step_info(step_name: str, result: dict, elapsed: float):
    print(f"[{step_name}] finished in {elapsed:.2f}s")
    if "llm_calls" in result:
        print(f"  LLM calls added: {result['llm_calls']}")
    if "execution_log" in result:
        print("  Log:")
        for log in result["execution_log"]:
            print(f"    - {log}")

def run_step_mode(raw_problem: dict, config: dict, skip_gen_tests: bool = False):
    """Manually execute nodes in sequence"""
    print_separator(f"Starting STEP mode (Skip Gen Tests: {skip_gen_tests})")
    
    # 1. Initialize State
    state = create_initial_state(raw_problem, config)
    
    # 2. Retrieve Knowledge
    start = time.time()
    res = retrieve_knowledge_node(state)
    state = manual_merge_state(state, res)
    print_step_info("retrieve_knowledge", res, time.time() - start)
    
    # 3. Generate Tests (or mock)
    if skip_gen_tests:
        print("\n[generate_tests] SKIPPED (Quick Mode)")
        # Mock generated tests using public tests
        public_tests = raw_problem.get("public_tests", [])
        mock_tests = {
            "tests": {
                "generated_tests": [
                    {"input": t.get("input", ""), "expected_output": t.get("output", ""), "type": "public"}
                    for t in public_tests
                ],
                "total_tests": len(public_tests),
            }
        }
        state = manual_merge_state(state, mock_tests)
    else:
        start = time.time()
        res = generate_tests_node(state)
        state = manual_merge_state(state, res)
        print_step_info("generate_tests", res, time.time() - start)

    # 4. Plan Solution
    start = time.time()
    res = plan_solution_node(state)
    state = manual_merge_state(state, res)
    print_step_info("plan_solution", res, time.time() - start)

    # 5. Iteration Loop
    max_steps = 10
    step_count = 0
    
    while step_count < max_steps:
        step_count += 1
        iteration = state.get("iteration", 0)
        print_separator(f"Iteration {iteration} (Step {step_count}/{max_steps})")
        
        # 5.1 Generate Code
        start = time.time()
        res = generate_code_node(state)
        state = manual_merge_state(state, res)
        print_step_info("generate_code", res, time.time() - start)
        
        # 5.2 Compile Code
        start = time.time()
        res = compile_code_node(state)
        state = manual_merge_state(state, res)
        print_step_info("compile_code", res, time.time() - start)
        
        # Print compilation errors if any
        if not state["solution"].get("compilation_success"):
            print("  Compilation Errors:")
            for err in state["solution"].get("compilation_errors", []):
                print(f"    - {err}")
        
        # 5.3 Routing: Compile Success?
        route = compilation_routing(state)
        print(f"  -> Compilation Routing: {route}")
        
        if route == "success":
            # 5.4 Run Tests
            start = time.time()
            res = run_tests_node(state)
            state = manual_merge_state(state, res)
            print_step_info("run_tests", res, time.time() - start)
            
            # 5.5 Unified Check
            start = time.time()
            res = unified_check_node(state)
            state = manual_merge_state(state, res)
            print_step_info("unified_check", res, time.time() - start)
            
            # 5.6 Routing: Status?
            status_route = status_routing(state)
            print(f"  -> Status Routing: {status_route}")
            
            if status_route == "end":
                print_separator("Workflow Ended")
                print(f"Final Status: {state.get('status')}")
                break
            else:
                # continue -> analyze feedback
                pass
        else:
            # Compilation failed -> analyze feedback
            pass

        # 5.7 Analyze Feedback
        print("\n[Flow] Proceeding to Analyze Feedback...")
        start = time.time()
        res = analyze_feedback_node(state)
        state = manual_merge_state(state, res)
        print_step_info("analyze_feedback", res, time.time() - start)
        
        # Loop back to Generate Code

    else:
        print_separator("Workflow Stopped (Max Steps Reached)")
        state["status"] = "max_steps_reached"

    return state

def run_workflow_mode(raw_problem: dict, config: dict):
    """Run using the actual LangGraph compiled workflow"""
    print_separator("Starting WORKFLOW mode")
    final_state = run_workflow(raw_problem, config)
    return final_state

def main():
    parser = argparse.ArgumentParser(description="Test Full Solvita Workflow")
    parser.add_argument("problem", help="Path to problem JSON file")
    parser.add_argument("--workflow", action="store_true", help="Run using LangGraph run_workflow()")
    parser.add_argument("--step", action="store_true", help="Run using manual step-by-step execution")
    parser.add_argument("--quick", action="store_true", help="Quick mode (skip generate_tests) for step mode")
    parser.add_argument("--model", default="claude-opus-4-5-20251101", help="LLM model to use")
    
    args = parser.parse_args()

    raw_problem = load_problem(args.problem)
    
    config = {
        "model": args.model,
        "temperature": 0.1,
        "max_iterations": 3,
        "base_url": "http://14.103.68.46/v1",
        "api_key": "sk-<redacted>",
    }
    
    start_time = time.time()
    final_state = {}

    if args.workflow:
        if args.quick:
            print("Warning: --quick is not supported in --workflow mode (workflow runs full graph). Ignoring --quick.")
        final_state = run_workflow_mode(raw_problem, config)
    elif args.step or args.quick:
        # --quick implies --step
        final_state = run_step_mode(raw_problem, config, skip_gen_tests=args.quick)
    else:
        print("Please specify --workflow, --step, or --quick")
        parser.print_help()
        sys.exit(1)

    elapsed = time.time() - start_time
    print_separator("Final Summary")
    print(f"Total Duration: {elapsed:.2f}s")
    print(f"Final Status: {final_state.get('status')}")
    print(f"Total LLM Calls: {final_state.get('llm_calls')}")
    
    sol = final_state.get("solution", {})
    if sol.get("code"):
        print(f"\nFinal Code ({len(sol['code'])} bytes):")
        print("-" * 20)
        print(sol["code"][:500] + ("..." if len(sol["code"]) > 500 else ""))
        print("-" * 20)

if __name__ == "__main__":
    main()
