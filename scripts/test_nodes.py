"""
测试 generate_tests / abstract_problem / generate_code 三个节点的端到端脚本

用法:
    # 完整模式：跑全部三个节点
    python -m scripts.test_nodes data/problems/codecontests_1575_A__Another_Sorting_Problem.json

    # 快速模式：跳过 generate_tests，只用 public_tests 测 plan + generate_code
    python -m scripts.test_nodes data/problems/codecontests_1575_A__Another_Sorting_Problem.json --quick

    # 列出所有可用题目
    python -m scripts.test_nodes --list
"""

import argparse
import json
import sys
import time
from pathlib import Path
from loguru import logger

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.state import create_initial_state, SolvitaState
from src.nodes.generate_tests import generate_tests_node
from src.nodes.abstract_problem import abstract_problem_node
from src.nodes.generate_code import generate_code_node


PROBLEMS_DIR = PROJECT_ROOT / "data" / "problems"


def list_problems():
    """列出所有可用题目"""
    files = sorted(PROBLEMS_DIR.glob("*.json"))
    if not files:
        print("No problems found in", PROBLEMS_DIR)
        return
    print(f"Available problems ({len(files)}):")
    for i, f in enumerate(files, 1):
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        name = data.get("_metadata", {}).get("name", f.stem)
        n_tests = len(data.get("public_tests", []))
        print(f"  {i}. {f.name}")
        print(f"     {name} | {n_tests} public test(s)")


def load_problem(path: str) -> dict:
    """加载题目 JSON"""
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        logger.error(f"Problem file not found: {p}")
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_state(state: dict, update: dict) -> dict:
    """模拟 LangGraph 的 merge_dict reducer，把节点返回值合并进 state"""
    from src.graph.state import merge_dict
    from operator import add as op_add

    # 定义哪些字段用什么 reducer
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
            new_state[key] = reducers[key](new_state.get(key, {} if key not in ("execution_log", "messages") else []), val)
        elif key == "llm_calls":
            new_state[key] = new_state.get(key, 0) + val
        else:
            new_state[key] = val
    return new_state


def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_state_summary(state: dict, label: str):
    """打印 state 关键字段摘要"""
    print(f"\n--- {label} ---")
    print(f"  LLM calls so far: {state.get('llm_calls', 0)}")
    print(f"  Execution log entries: {len(state.get('execution_log', []))}")

    # tests
    tests = state.get("tests", {})
    gen_tests = tests.get("generated_tests", [])
    if gen_tests:
        with_output = sum(1 for t in gen_tests if t.get("expected_output"))
        print(f"  Generated tests: {len(gen_tests)} ({with_output} with expected_output)")

    # plan
    plan = state.get("plan", {})
    algo = plan.get("algorithm_choice", "")
    steps = plan.get("implementation_steps", [])
    if algo:
        print(f"  Algorithm: {algo}")
        print(f"  Steps: {len(steps)}")

    # solution
    sol = state.get("solution", {})
    code = sol.get("code", "")
    if code:
        lines = code.strip().splitlines()
        print(f"  Code: {len(lines)} lines")

    # recent log
    logs = state.get("execution_log", [])
    if logs:
        recent = logs[-5:]
        print(f"  Recent logs:")
        for l in recent:
            print(f"    {l}")


def run_generate_tests(raw_problem: dict, config: dict) -> tuple[dict, dict]:
    """只跑 generate_tests_node"""
    print_separator("1. Running generate_tests_node")
    start = time.time()

    state = create_initial_state(raw_problem, config)
    result = generate_tests_node(state)

    elapsed = time.time() - start
    new_state = merge_state(state, result)

    print(f"  Duration: {elapsed:.1f}s")
    print(f"  LLM calls: {result.get('llm_calls', 0)}")
    print_state_summary(new_state, "After generate_tests")

    return new_state, result


def run_abstract_problem(raw_problem: dict, config: dict) -> tuple[dict, dict]:
    """Run abstract_problem_node on initial state."""
    print_separator("2. Running abstract_problem_node")
    start = time.time()

    state = create_initial_state(raw_problem, config)
    result = abstract_problem_node(state)

    elapsed = time.time() - start
    new_state = merge_state(state, result)

    print(f"  Duration: {elapsed:.1f}s")
    print(f"  LLM calls: {result.get('llm_calls', 0)}")
    print_state_summary(new_state, "After abstract_problem")

    return new_state, result


def run_abstract_problem_from_state(state: dict, config: dict) -> tuple[dict, dict]:
    """Run abstract_problem_node on existing state."""
    print_separator("2. Running abstract_problem_node (from existing state)")
    start = time.time()

    result = abstract_problem_node(state)

    elapsed = time.time() - start
    new_state = merge_state(state, result)

    print(f"  Duration: {elapsed:.1f}s")
    print(f"  LLM calls: {result.get('llm_calls', 0)}")
    print_state_summary(new_state, "After abstract_problem")

    return new_state, result


def run_generate_code(raw_problem: dict, config: dict, pre_state: dict = None) -> tuple[dict, dict]:
    """跑 generate_code_node，可选 pre_state（用于串联）"""
    print_separator("3. Running generate_code_node")
    start = time.time()

    if pre_state is not None:
        # 从 pre_state 继续
        state = pre_state
    else:
        # From initial state, run abstract_problem first
        state = create_initial_state(raw_problem, config)
        abs_result = abstract_problem_node(state)
        state = merge_state(state, abs_result)

    result = generate_code_node(state)

    elapsed = time.time() - start
    new_state = merge_state(state, result)

    print(f"  Duration: {elapsed:.1f}s")
    print(f"  LLM calls: {result.get('llm_calls', 0)}")
    print_state_summary(new_state, "After generate_code")

    # 打印自验证 log
    exec_log = result.get("execution_log", [])
    print("\n  Self-validation logs:")
    for line in exec_log:
        print(f"    {line}")

    return new_state, result


def run_full_pipeline(raw_problem: dict, config: dict) -> dict:
    """完整跑一遍三个节点"""
    print_separator("Starting FULL pipeline: generate_tests → abstract_problem → generate_code")

    # Step 1: generate_tests
    state, _ = run_generate_tests(raw_problem, config)

    # Step 2: abstract_problem - pass state instead of raw_problem to preserve generate_tests result
    state, _ = run_abstract_problem_from_state(state, config)

    # Step 3: generate_code
    state, _ = run_generate_code(raw_problem, config, pre_state=state)

    return state


def run_quick_mode(raw_problem: dict, config: dict) -> dict:
    """Quick mode: skip generate_tests, run abstract_problem + generate_code."""
    print_separator("Starting QUICK mode: abstract_problem → generate_code (skip generate_tests)")

    # 模拟 generate_tests 的输出（只用 public_tests）
    public_tests = raw_problem.get("public_tests", [])
    mock_tests_state = {
        "tests": {
            "generated_tests": [
                {"input": t.get("input", ""), "expected_output": t.get("output", ""), "type": "public"}
                for t in public_tests
            ],
            "total_tests": len(public_tests),
        }
    }

    # Step 1: abstract_problem
    state, _ = run_abstract_problem(raw_problem, config)
    # merge mock tests
    state = merge_state(state, mock_tests_state)

    # Step 2: generate_code
    state, _ = run_generate_code(raw_problem, config, pre_state=state)

    return state


def main():
    parser = argparse.ArgumentParser(
        description="Test generate_tests / abstract_problem / generate_code nodes"
    )
    parser.add_argument("problem", nargs="?", help="Path to problem JSON file")
    parser.add_argument("--quick", action="store_true", help="Quick mode: skip generate_tests")
    parser.add_argument("--list", action="store_true", help="List available problems")
    parser.add_argument("--model", default=None, help="LLM model to use (optional, defaults to config/models.yaml)")
    parser.add_argument("--max-iters", type=int, default=3, help="Max iterations")

    args = parser.parse_args()

    if args.list:
        list_problems()
        return

    if not args.problem:
        parser.print_help()
        print("\nError: No problem file specified")
        sys.exit(1)

    # Load problem
    print(f"Loading problem: {args.problem}")
    raw_problem = load_problem(args.problem)

    # Config
    config = {
        "temperature": 0.1,
        "max_tokens": 128000,
        "max_iterations": args.max_iters,
    }
    if args.model:
        config["model"] = args.model

    # Run
    start_all = time.time()
    if args.quick:
        state = run_quick_mode(raw_problem, config)
    else:
        state = run_full_pipeline(raw_problem, config)

    elapsed = time.time() - start_all
    print_separator("Complete!")
    print(f"  Total duration: {elapsed:.1f}s")
    print(f"  Final LLM calls: {state.get('llm_calls', 0)}")
    print(f"  Status: {state.get('status', 'unknown')}")

    # Print final code if available
    code = state.get("solution", {}).get("code", "")
    if code:
        print(f"\n--- Final Generated Code ({len(code)} bytes) ---")
        # Only print first 2000 chars to avoid flooding
        if len(code) > 2000:
            print(code[:2000] + "\n... [truncated]")
        else:
            print(code)


if __name__ == "__main__":
    main()

