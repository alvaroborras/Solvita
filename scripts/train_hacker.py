#!/usr/bin/env python3
"""
scripts/train_hacker.py — 离线训练 Hacker Memory (Native Driver)

用途：
    从 dataset 批量读取题目，组装初始 SolvitaState，将 bug 代码注入，
    直接驱动现有的 `hack_test_node` 和 `update_hacker_memory_node`。
    以此评估 Hacker 攻击策略在真实业务管线中的表现。

用法：
    python scripts/train_hacker.py \\
        --dataset <workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl \\
        --limit 200 \\
        --data-dir data/memory
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# 加入项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.llm import UnifiedLLMClient
from src.graph.state import SolvitaState, create_initial_state
from src.nodes.hack_test import hack_test_node
from src.nodes.update_hacker_memory import update_hacker_memory_node


# ─────────────────────────────────────────────────────────────
# 单道题训练 (Driver Wrap)
# ─────────────────────────────────────────────────────────────

def train_one_hacker(item: dict, config: dict, trial_idx: int) -> dict:
    problem_id = item.get("id", f"item_{trial_idx}")
    description = item.get("description", "")
    incorrect_solutions = item.get("incorrect_solution", [])

    if not description or not incorrect_solutions:
        return {"id": problem_id, "skipped": True, "reason": "no description or incorrect_solution"}

    buggy_code = incorrect_solutions[0].get("code", "")
    if not buggy_code:
        return {"id": problem_id, "skipped": True, "reason": "empty buggy code"}

    # 1. 伪造初始 State
    # 这里要模拟成：TestGen 已经成功跑完了，并且 CodeGen 写出了一个 buggy 的实现。
    raw_problem = {
        "description": description,
        "time_limit": 2000,
        "space_limit": 256,
        "public_tests": [{"input": "some stdin", "output": "some stdout"}]
    }
    state = create_initial_state(raw_problem, config)
    state["iteration"] = trial_idx
    
    # 强制注入有 bug 的代码作为当前系统的 Solution
    state["solution"]["solution_cpp"] = buggy_code
    
    # 假设此时是 hack 阶段的第 1 轮
    state["hack_round"] = 0
    state["hack_failures"] = []
    
    try:
        # 2. 直接调用真实的 Hacker 节点
        # 这会自动获取 Memory 注入、生成对抗测试、尝试通过沙盒运行。
        logger.info(f"[{problem_id}] Entering hack_test_node...")
        new_state_delta = hack_test_node(state)
        
        # 合并产出回 State
        state.update(new_state_delta)
        
        # 3. 提取结果
        hack_passed = state.get("hack_passed", True)  # True =没找到Bug/过了测试; False =成功触发WA/RE
        hacker_ids = state.get("hacker_memory_item_ids", [])
        
        if not hack_passed:
            # 找到 BUG 了！Hack 成功，拿奖励！
            reward = 1.0
            logger.info(f"[{problem_id}] Hack SUCCEEDED (Found bug)! Reward: +1.0")
        else:
            # 没找到 Bug 
            if state.get("hack_round", 0) >= state.get("max_hack_rounds", 3):
                reward = -0.5
                logger.info(f"[{problem_id}] Hack exhausted all rounds without finding bug. Reward: -0.5")
            else:
                reward = -1.0
                logger.warning(f"[{problem_id}] Hack pipeline aborted or no valid test found. Reward: -1.0")
        
        # 强制设置 reward 到 state 里供 update 节点使用 
        state["hacker_reward"] = reward

        # 4. 调用原生内存更新节点
        logger.info(f"[{problem_id}] Settle via update_hacker_memory_node...")
        update_hacker_memory_node(state)
        
        return {
            "id": problem_id, 
            "reward": reward, 
            "hack_success": not hack_passed, 
            "hacker_ids": hacker_ids
        }

    except Exception as e:
        logger.error(f"[{problem_id}] Pipeline exception: {e}")
        return {"id": problem_id, "reward": -1.0, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hacker 对抗攻击离线训练 (Native Node Wrappers)")
    parser.add_argument("--dataset", default="<workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 道题")
    parser.add_argument("--data-dir", default="data/memory", help="SQLite 存储目录")
    parser.add_argument("--tags", nargs="*", help="只训练包含这些 tag 的题目")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 条")
    args = parser.parse_args()

    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": args.data_dir,
            "hack_top_k": 3,
        }
    }

    # 提前初始化默认 LLM client 放全局
    from src.llm.unified_client import UnifiedLLMClient, set_default_client
    llm = UnifiedLLMClient(config)
    set_default_client(llm)

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"数据集不存在: {dataset_path}")
        sys.exit(1)

    results = []
    processed = 0

    logger.info(f"开始 Hacker 离线训练 (Native Nodes Driver): {dataset_path}")

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

            result = train_one_hacker(item, config, trial_idx=processed)
            results.append(result)
            processed += 1

            if processed % 5 == 0:
                rewards = [r["reward"] for r in results if "reward" in r]
                successes = sum(1 for r in results if r.get("hack_success"))
                avg = sum(rewards) / len(rewards) if rewards else 0
                logger.info(f"已处理 {processed} 道 | avg reward: {avg:+.3f} | hack 成功: {successes} 道")

    # 汇总
    rewards = [r["reward"] for r in results if "reward" in r]
    successes = sum(1 for r in results if r.get("hack_success"))
    logger.info("=" * 50)
    logger.info(f"训练完成: {processed} 道题")
    logger.info(f"Hack 成功率: {successes}/{processed} ({successes/processed*100:.1f}%)" if processed else "")
    logger.info(f"平均 reward: {sum(rewards)/len(rewards):+.3f}" if rewards else "无有效结果")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
