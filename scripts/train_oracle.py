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
# Phase 1: Worker — 重计算（LLM + C++ 编译/对拍），可并行
# ─────────────────────────────────────────────────────────────

def _worker_generate(item: dict, config: dict, trial_idx: int, tmp_dir: str = None) -> dict:
    """
    Worker function: runs generate_tests_node + verify.
    Returns a result dict with reward and state snapshot for settlement.
    This function does NOT write to the SQLite memory database.
    """
    # Re-init LLM client in child process (not inherited across fork)
    from src.llm.unified_client import UnifiedLLMClient, set_default_client
    llm = UnifiedLLMClient(config)
    set_default_client(llm)

    problem_id = item.get("id", f"item_{trial_idx}")
    description = item.get("description", "")
    correct_solutions = item.get("correct_solution", []) or []
    public_tests = item.get("test_case") or []

    if not description or not correct_solutions:
        return {"id": problem_id, "skipped": True, "reason": "no description or correct_solution"}

    raw_problem = {
        "id": problem_id,
        "_metadata": {"problem_id": problem_id},
        "description": description,
        "time_limit": 2000,
        "space_limit": 256,
        "public_tests": public_tests,
    }
    state = create_initial_state(raw_problem, config)
    state["iteration"] = trial_idx

    try:
        with tempfile.TemporaryDirectory(dir=tmp_dir) as tmpdir:
            tmp = Path(tmpdir)

            runner = resolve_correct_runner(correct_solutions, tmp)
            if runner is not None:
                state["training_mode"] = True
                state["training_runner"] = runner
                logger.info(f"[{problem_id}] Training mode: correct_solution runner ready ({runner[0]})")
            else:
                logger.warning(f"[{problem_id}] No usable correct_solution — training mode disabled")

            logger.info(f"[{problem_id}] Entering generate_tests_node...")
            new_state_delta = generate_tests_node(state)
            state.update(new_state_delta)

            tests = state.get("tests", {})
            generated_list = tests.get("generated_tests", [])
            oracle_ids = state.get("oracle_memory_item_ids", [])

            if tests.get("ready", False) and generated_list:
                certified_count = sum(1 for t in generated_list if t.get("type") == "generated")
                cert_ratio = tests.get("cert_ratio", 1.0 if certified_count > 0 else 0.0)

                if certified_count == 0:
                    has_crash = "crashed" in tests.get("cert_ratio_note", "")
                    if has_crash:
                        logger.warning(f"[{problem_id}] All solvers CRASHED — penalty reward -1.00")
                        reward = -1.0
                    else:
                        logger.warning(f"[{problem_id}] All solvers failed self-check — penalty reward -0.70")
                        reward = -0.7
                elif cert_ratio >= 1.0:
                    reward = verify_generated_tests(generated_list, correct_solutions, tmp)
                    logger.info(f"[{problem_id}] Fully certified ({certified_count} tests). Reward: {reward:+.2f}")
                else:
                    reward = round(cert_ratio * 0.9, 2)
                    logger.info(f"[{problem_id}] Partially certified ({certified_count}/200, {cert_ratio:.1%}). Reward: {reward:+.2f}")
            else:
                logger.warning(f"[{problem_id}] TestGen pipeline failed (tests.ready=False)")
                reward = -0.6

            # Prepare state snapshot for settlement (Phase 2)
            pass_rate = max(0.0, min(1.0, (reward + 1.0) / 2.0))

            return {
                "id": problem_id,
                "reward": reward,
                "oracle_ids": oracle_ids,
                "pass_rate": pass_rate,
                # Minimal state snapshot for update_oracle_memory_node
                "state_snapshot": {
                    "config": config,
                    "iteration": trial_idx,
                    "problem": state.get("problem", {}),
                    "oracle_memory_item_ids": oracle_ids,
                    "tests": {"pass_rate": pass_rate},
                    "status": state.get("status", "pending"),
                },
            }

    except Exception as e:
        logger.error(f"[{problem_id}] Pipeline exception: {e}")
        return {"id": problem_id, "reward": -1.0, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# Phase 2: Settlement — 串行写入 SQLite（主进程执行）
# ─────────────────────────────────────────────────────────────

def _settle_memory(result: dict):
    """Settle memory rewards in main process (serial, no SQLite lock risk)."""
    if result.get("skipped") or result.get("error"):
        return
    state_snapshot = result.get("state_snapshot")
    if not state_snapshot:
        return
    try:
        logger.info(f"[{result['id']}] Settle via update_oracle_memory_node...")
        update_oracle_memory_node(state_snapshot)
    except Exception as e:
        logger.error(f"[{result['id']}] Settlement exception: {e}")


# ─────────────────────────────────────────────────────────────
# 向后兼容：单线程模式 (workers=1)
# ─────────────────────────────────────────────────────────────

def train_one_oracle(item: dict, config: dict, trial_idx: int, tmp_dir: str = None) -> dict:
    """Legacy single-threaded entry: generate + settle in one call."""
    result = _worker_generate(item, config, trial_idx, tmp_dir=tmp_dir)
    _settle_memory(result)
    return result


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    parser = argparse.ArgumentParser(description="Oracle TestGen 离线训练 (Native Node Wrappers)")
    parser.add_argument("--dataset", default="<workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 道题")
    parser.add_argument("--data-dir", default="data/memory", help="SQLite 内存存储目录")
    parser.add_argument("--tags", nargs="*", help="只训练包含这些 tag 的题目")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 条")
    parser.add_argument("--workers", type=int, default=1, help="并行 worker 数 (默认 1 = 单线程)")
    parser.add_argument("--tmp-dir", default=None, help="临时文件存放目录 (建议设在大盘路径，防止 /tmp 爆满)")
    args = parser.parse_args()

    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": args.data_dir,
            "oracle_top_k": 3,
        }
    }
    
    # 主进程初始化 LLM client（单线程模式用；多进程模式下 worker 会自行初始化）
    from src.llm.unified_client import UnifiedLLMClient, set_default_client
    llm = UnifiedLLMClient(config)
    set_default_client(llm)

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"数据集不存在: {dataset_path}")
        sys.exit(1)

    # ── 预加载符合条件的题目到内存 ──────────────────────────
    items_to_process = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            if line_idx < args.skip:
                continue
            if not line.strip():
                continue
            if args.limit and len(items_to_process) >= args.limit:
                break
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.tags:
                item_tags = set(item.get("tags", []))
                if not item_tags.intersection(set(args.tags)):
                    continue
            items_to_process.append(item)

    total = len(items_to_process)
    logger.info(f"开始 Oracle 离线训练: {dataset_path}")
    logger.info(f"  范围: skip={args.skip}, limit={args.limit or 'ALL'}, 实际加载={total} 道")
    logger.info(f"  并行: workers={args.workers}")

    results = []

    if args.workers <= 1:
        # ── 单线程模式（向后兼容）──────────────────────────
        for idx, item in enumerate(items_to_process):
            result = train_one_oracle(item, config, trial_idx=idx, tmp_dir=args.tmp_dir)
            results.append(result)
            if (idx + 1) % 5 == 0:
                rewards = [r["reward"] for r in results if "reward" in r]
                avg = sum(rewards) / len(rewards) if rewards else 0
                logger.info(f"已处理 {idx + 1}/{total} 道 | 平均 reward: {avg:+.3f}")
    else:
        # ── 多进程模式 ─────────────────────────────────────
        logger.info(f"启动 {args.workers} 个 worker 进程...")
        settled = 0
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_idx = {}
            for idx, item in enumerate(items_to_process):
                future = executor.submit(_worker_generate, item, config, idx, tmp_dir=args.tmp_dir)
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                except Exception as e:
                    problem_id = items_to_process[idx].get("id", f"item_{idx}")
                    logger.error(f"[{problem_id}] Worker exception: {e}")
                    result = {"id": problem_id, "reward": -1.0, "error": str(e)}

                # Phase 2: 串行结算（主进程，安全写入 SQLite）
                _settle_memory(result)
                results.append(result)
                settled += 1

                if settled % 5 == 0:
                    rewards = [r["reward"] for r in results if "reward" in r]
                    avg = sum(rewards) / len(rewards) if rewards else 0
                    logger.info(f"已完成 {settled}/{total} 道 | 平均 reward: {avg:+.3f}")

    # ── 汇总 ─────────────────────────────────────────────
    rewards = [r["reward"] for r in results if "reward" in r]
    skipped = sum(1 for r in results if r.get("skipped"))
    errors = sum(1 for r in results if r.get("error"))
    logger.info("=" * 50)
    logger.info(f"训练完成: {total} 道题 (跳过={skipped}, 异常={errors})")
    logger.info(f"平均 reward: {sum(rewards)/len(rewards):+.3f}" if rewards else "无有效结果")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
