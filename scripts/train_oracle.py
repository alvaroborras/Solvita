#!/usr/bin/env python3
"""
scripts/train_oracle.py — 离线训练 Oracle 暴力 Solver Memory (Native Driver)

用途：
    从 dataset 批量读取题目，组装初始 SolvitaState，直接驱动现有的 
    `generate_tests_node` 和 `update_oracle_memory_node` 跑通测试套件生成全流程。
    以此评估 Oracle C++ 模板在真实业务管线中的表现。

用法：
    python scripts/train_oracle.py \\
        --dataset <workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl \\
        --limit 200 \\
        --data-dir data/memory
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# 加入项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.llm import UnifiedLLMClient
from src.graph.state import SolvitaState, create_initial_state
from src.nodes.generate_tests import generate_tests_node
from src.nodes.update_oracle_memory import update_oracle_memory_node
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits


import ast
import subprocess as _subprocess


# ─────────────────────────────────────────────────────────────
# 正确解运行器解析：遍历所有 correct_solutions，取第一个能成功编译或运行的
# ─────────────────────────────────────────────────────────────

def resolve_correct_runner(correct_solutions: list, tmpdir: Path):
    """
    遍历 correct_solutions，返回第一个可用的运行器描述:
      - ("cpp", Path)       — C++ 可执行文件
      - ("python", Path)    — Python3 脚本

    策略：对每个 solution 依次：
      1. 尝试 g++ 编译为 C++ 可执行文件
      2. 如果编译失败→ 尝试 ast.parse() 检测是否合法 Python 3
      3. 两者均失败 → 跳过该 solution

    Returns:
        ("cpp", Path) | ("python", Path) 或 None
    """
    for idx, sol in enumerate(correct_solutions):
        code = sol.get("code", "") if isinstance(sol, dict) else str(sol)
        if not code.strip():
            continue

        # Strategy 1: Try C++ compile
        cpp_src = tmpdir / f"correct_{idx}.cpp"
        cpp_exe = tmpdir / f"correct_{idx}"
        cpp_src.write_text(code, encoding="utf-8")
        ok, _ = compile_cpp(cpp_src, cpp_exe)
        if ok:
            logger.debug(f"[RUNNER] Solution {idx}: compiled as C++")
            return ("cpp", cpp_exe)

        # Strategy 2: Try Python 3 (AST parse check)
        try:
            ast.parse(code)
            py_src = tmpdir / f"correct_{idx}.py"
            py_src.write_text(code, encoding="utf-8")
            logger.debug(f"[RUNNER] Solution {idx}: identified as Python 3")
            return ("python", py_src)
        except SyntaxError:
            pass

        logger.warning(f"[RUNNER] Solution {idx}: neither C++ nor Python 3, skipping")

    return None  # 全部失败


def _run_correct(runner, inp: str):
    """
    统一调用接口：根据 runner 类型执行正确解并返回 (returncode, stdout)。
    """
    kind, path = runner
    limits = ExecutionLimits.default_run()
    if kind == "cpp":
        # run_program 签名: (exe_path: Path, input_text, args=None, limits=None)
        rc, stdout, _ = run_program(path, inp, limits=limits)
        return rc, stdout
    else:
        # Python3: 用 subprocess 直接调
        try:
            result = _subprocess.run(
                ["python3", str(path)],
                input=inp,
                capture_output=True,
                text=True,
                timeout=limits.wall_seconds or 10,
            )
            return result.returncode, result.stdout
        except _subprocess.TimeoutExpired:
            return 124, ""
        except Exception as e:
            return -1, ""


# ─────────────────────────────────────────────────────────────
# 对拍验证：生成的测试用例 vs 数据集里的 correct_solution
# ─────────────────────────────────────────────────────────────

def verify_generated_tests(tests: list, correct_solutions: list, tmpdir: Path) -> float:
    """
    用 correct_solutions 中第一个可用的解校验节点生成的测试用例 output。
    返回 reward 信号。
    """
    if not tests:
        return -0.5  # 节点没能生成任何测试用例

    runner = resolve_correct_runner(correct_solutions, tmpdir)
    if runner is None:
        logger.warning("All correct_solutions failed to compile/parse. Skipping cross-check.")
        return 0.0  # 数据集质量问题，不惩罚训练

    mismatches = 0
    passed = 0
    for test in tests:
        inp = test.get("input", "")
        expected_out = test.get("expected_output") or test.get("output", "")

        rc, c_out = _run_correct(runner, inp)
        if rc == 0 and expected_out.strip() == c_out.strip():
            passed += 1
        else:
            mismatches += 1

    if mismatches == 0 and passed > 0:
        return 1.0  # 完全正确
    elif passed > 0:
        return -0.2  # 部分错误
    else:
        return -0.5  # 全错



# ─────────────────────────────────────────────────────────────
# 单道题训练 (Driver Wrap)
# ─────────────────────────────────────────────────────────────

def train_one_oracle(item: dict, config: dict, trial_idx: int) -> dict:
    problem_id = item.get("id", f"item_{trial_idx}")
    description = item.get("description", "")
    correct_solutions = item.get("correct_solution", []) or []
    public_tests = item.get("test_case") or []

    if not description or not correct_solutions:
        return {"id": problem_id, "skipped": True, "reason": "no description or correct_solution"}
    # 1. 伪造初始 State
    raw_problem = {
        "id": problem_id,
        "_metadata": {"problem_id": problem_id},
        "description": description,
        "time_limit": 2000,
        "space_limit": 256,
        "public_tests": public_tests,  # Fix 1: 真实外部样例（可以为空列表）
    }
    state = create_initial_state(raw_problem, config)
    state["iteration"] = trial_idx

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            
            # 2. 直接调用真实的 TestGen 节点
            # 注入 training_runner，让节点内部用 correct_solution 做微测试对拍
            runner = resolve_correct_runner(correct_solutions, tmp)
            if runner is not None:
                state["training_mode"] = True
                state["training_runner"] = runner
                logger.info(f"[{problem_id}] Training mode: correct_solution runner ready ({runner[0]})")
            else:
                logger.warning(f"[{problem_id}] No usable correct_solution — training mode disabled")

            logger.info(f"[{problem_id}] Entering generate_tests_node...")
            new_state_delta = generate_tests_node(state)
            
            # 合并产出回 State
            state.update(new_state_delta)
            
            # 3. 提取结果
            tests = state.get("tests", {})
            generated_list = tests.get("generated_tests", [])
            oracle_ids = state.get("oracle_memory_item_ids", [])
            
            if tests.get("ready", False) and generated_list:
                # TestGen 管线成功完赛，开始交叉校验
                reward = verify_generated_tests(generated_list, correct_solutions, tmp)  # Fix 3: 传全部 solutions
                logger.info(f"[{problem_id}] TestGen success. Cross-check reward: {reward:+.2f}")
            else:
                # TestGen 管线中途崩溃（generator错/validator错/solver编译错等）
                logger.warning(f"[{problem_id}] TestGen pipeline failed (tests.ready=False)")
                reward = -0.6
                
            # 4. 手动覆盖 state 里的 tests.pass_rate 供 update_oracle_memory_node 使用
            # 因为原生的 update_oracle 节点是看 tests.pass_rate 来打分的，
            # 我们在这里利用对拍结果，强制设置该分数为我们的奖励信号映射值。
            if "tests" not in state:
                state["tests"] = {}
                
            if reward > 0:
                state["tests"]["pass_rate"] = 1.0     # 满分
            elif reward == 0:
                state["tests"]["pass_rate"] = 0.5     # 中立
            else:
                state["tests"]["pass_rate"] = 0.0     # 惩罚

            # 5. 调用原生的内存更新节点进行结算
            logger.info(f"[{problem_id}] Settle via update_oracle_memory_node...")
            update_oracle_memory_node(state)
            
            return {"id": problem_id, "reward": reward, "oracle_ids": oracle_ids}

    except Exception as e:
        logger.error(f"[{problem_id}] Pipeline exception: {e}")
        return {"id": problem_id, "reward": -1.0, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Oracle TestGen 离线训练 (Native Node Wrappers)")
    parser.add_argument("--dataset", default="<workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 道题")
    parser.add_argument("--data-dir", default="data/memory", help="SQLite 内存存储目录")
    parser.add_argument("--tags", nargs="*", help="只训练包含这些 tag 的题目")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 条")
    args = parser.parse_args()

    # 传递给 create_initial_state 的 config
    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": args.data_dir,
            "oracle_top_k": 3,
        }
    }
    
    # 提前初始化默认 LLM client 放到全局 (确保节点内可以 get_default_client())
    from src.llm.unified_client import UnifiedLLMClient, set_default_client
    llm = UnifiedLLMClient(config)
    set_default_client(llm)

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"数据集不存在: {dataset_path}")
        sys.exit(1)

    results = []
    processed = 0

    logger.info(f"开始 Oracle 离线训练 (Native Nodes Driver): {dataset_path}")

    with open(dataset_path, "r", encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            if line_idx < args.skip:
                continue
            if not line.strip():
                continue
            if args.limit and processed >= args.limit:
                break

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            if args.tags:
                item_tags = set(item.get("tags", []))
                if not item_tags.intersection(set(args.tags)):
                    continue

            result = train_one_oracle(item, config, trial_idx=processed)
            results.append(result)
            processed += 1

            if processed % 5 == 0:
                rewards = [r["reward"] for r in results if "reward" in r]
                avg = sum(rewards) / len(rewards) if rewards else 0
                logger.info(f"已处理 {processed} 道 | 平均 reward: {avg:+.3f}")

    # 汇总
    rewards = [r["reward"] for r in results if "reward" in r]
    logger.info("=" * 50)
    logger.info(f"训练完成: {processed} 道题")
    logger.info(f"平均 reward: {sum(rewards)/len(rewards):+.3f}" if rewards else "无有效结果")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
