#!/usr/bin/env python3
"""
scripts/train_oracle.py — 离线训练 Oracle 暴力 Solver Memory

用途：
    从 solvita_train_tanh.jsonl 批量读取题目，让 LLM 用 ORACLE 模板库生成 C++17
    暴力解并与 correct_solution 对拍，将奖励信号写入 ORACLE SQLite，完成冷启动。

用法：
    python scripts/train_oracle.py \\
        --dataset <workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl \\
        --limit 200 \\
        --data-dir data/memory \\
        --config config/default.yaml
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
from src.memory import MemoryClient, MemoryNamespace, Observation
from src.memory.types import MemoryEvent
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits
from src.utils.json_utils import parse_json_response
from datetime import datetime


# ─────────────────────────────────────────────────────────────
# 构建训练 Prompt
# ─────────────────────────────────────────────────────────────

def build_oracle_prompt(description: str, memory_advice: str) -> str:
    advice_section = f"\n=== BRUTE FORCE TEMPLATES (few-shot) ===\n{memory_advice}\n=========================================\n" if memory_advice else ""
    return f"""You are a competitive programming judge writing a BRUTE FORCE reference solution.
This solution must be 100% correct, even if slow.

Problem:
{description}
{advice_section}
Write a complete C++17 brute force solution. It must:
- Include all headers
- Read from stdin, write to stdout
- Be 100% correct (exhaustive / naive approach)
- Compile with: g++ -O2 -std=c++17

Return ONLY a JSON object:
{{
    "solver_cpp": "<complete C++ source code>"
}}
"""


# ─────────────────────────────────────────────────────────────
# 对拍：brute vs correct_solution
# ─────────────────────────────────────────────────────────────

def cross_validate(brute_exe: str, correct_code: str, public_tests: list, tmpdir: Path) -> float:
    """
    把 brute 的输出与 correct_solution 编译出的 correct_exe 对拍。
    返回 reward: +1.0 全部一致 / -0.5 有差异 / -0.3 编译/运行失败。
    """
    # 编译 correct_solution
    correct_src = tmpdir / "correct.cpp"
    correct_exe = tmpdir / "correct"
    correct_src.write_text(correct_code, encoding="utf-8")
    ok, _ = compile_cpp(correct_src, correct_exe)
    if not ok:
        logger.warning("correct_solution 编译失败，跳过对拍")
        return 0.0  # 无法判断，不惩罚

    # 对每个公共测试对拍
    mismatches = 0
    for i, test in enumerate(public_tests[:5]):  # 最多用 5 个样例
        inp = test.get("input", "")

        code_b, out_b, _ = run_program(Path(brute_exe), inp, ExecutionLimits.default_run())
        code_c, out_c, _ = run_program(correct_exe, inp, ExecutionLimits.default_run())

        if code_b != 0 or code_c != 0:
            mismatches += 1
            continue

        if out_b.strip() != out_c.strip():
            mismatches += 1

    if not public_tests:
        return 0.5  # 没有公共测试，给中立分
    if mismatches == 0:
        return 1.0
    elif mismatches <= len(public_tests) // 2:
        return -0.3
    else:
        return -0.5


# ─────────────────────────────────────────────────────────────
# 单道题训练
# ─────────────────────────────────────────────────────────────

def train_one_oracle(item: dict, llm: "UnifiedLLMClient", config: dict, trial_idx: int) -> dict:
    problem_id = item.get("id", f"item_{trial_idx}")
    description = item.get("description", "")
    correct_solutions = item.get("correct_solution", [])
    public_tests = item.get("public_tests", [])  # 部分数据集提供

    if not description or not correct_solutions:
        return {"id": problem_id, "skipped": True, "reason": "no description or correct_solution"}

    # 初始化 Memory Client
    memory = MemoryClient(
        namespace=MemoryNamespace.ORACLE,
        config=config,
        problem_desc=description,
    )

    # 1. 获取 Oracle 注入提示
    advice, item_ids = memory.get_injection(
        fsm_state="ORACLE_GEN",
        failure_type=None,
        attempt_count=trial_idx,
    )

    # 2. LLM 生成暴力解
    prompt = build_oracle_prompt(description, advice)
    response = llm.generate(prompt)

    try:
        data = parse_json_response(response)
        solver_cpp = data.get("solver_cpp", "")
    except Exception as e:
        logger.warning(f"[{problem_id}] LLM 解析失败: {e}")
        _settle(memory, item_ids, -0.3, trial_idx, description)
        return {"id": problem_id, "reward": -0.3, "error": "parse_failed"}

    # 3. 编译暴力解
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "brute.cpp"
        exe = tmp / "brute"
        src.write_text(solver_cpp, encoding="utf-8")
        ok, compile_log = compile_cpp(src, exe)

        if not ok:
            logger.warning(f"[{problem_id}] 编译失败")
            _settle(memory, item_ids, -0.5, trial_idx, description)
            return {"id": problem_id, "reward": -0.5, "error": "compile_failed"}

        # 4. 对拍
        correct_code = correct_solutions[0].get("code", "")
        reward = cross_validate(str(exe), correct_code, public_tests, tmp)

    logger.info(f"[{problem_id}] Oracle reward = {reward:+.2f}")
    _settle(memory, item_ids, reward, trial_idx, description)
    return {"id": problem_id, "reward": reward}


def _settle(memory: MemoryClient, item_ids: list, reward: float, iteration: int, problem_desc: str):
    """写入 SQLite 奖励记录。"""
    obs = Observation(
        fsm_state="ORACLE_SETTLE",
        attempt_count=iteration,
        raw_problem_desc=problem_desc,
    )
    memory.log_event(obs, item_ids, reward, iteration=iteration)


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Oracle 暴力 Solver 离线训练")
    parser.add_argument("--dataset", default="<workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 道题（默认不限）")
    parser.add_argument("--data-dir", default="data/memory", help="SQLite 内存存储目录")
    parser.add_argument("--tags", nargs="*", help="只训练包含这些 tag 的题目（可多选）")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 条（断点续训）")
    args = parser.parse_args()

    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": args.data_dir,
            "oracle_top_k": 3,
        },
        "llm": {},
    }

    llm = UnifiedLLMClient(config)

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"数据集不存在: {dataset_path}")
        sys.exit(1)

    results = []
    processed = 0
    skipped_lines = 0

    logger.info(f"开始 Oracle 离线训练: {dataset_path}")
    logger.info(f"limit={args.limit}, skip={args.skip}, data-dir={args.data_dir}")

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
                skipped_lines += 1
                continue

            # Tag 过滤
            if args.tags:
                item_tags = set(item.get("tags", []))
                if not item_tags.intersection(set(args.tags)):
                    continue

            result = train_one_oracle(item, llm, config, trial_idx=processed)
            results.append(result)
            processed += 1

            if processed % 10 == 0:
                rewards = [r["reward"] for r in results if "reward" in r]
                avg = sum(rewards) / len(rewards) if rewards else 0
                logger.info(f"进度: {processed} 道题 | 平均 reward: {avg:+.3f}")

    # 汇总
    rewards = [r["reward"] for r in results if "reward" in r]
    logger.info("=" * 50)
    logger.info(f"训练完成: {processed} 道题")
    logger.info(f"平均 reward: {sum(rewards)/len(rewards):+.3f}" if rewards else "无有效结果")
    logger.info(f"正向 (+): {sum(1 for r in rewards if r > 0)} 道")
    logger.info(f"负向 (-): {sum(1 for r in rewards if r < 0)} 道")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
