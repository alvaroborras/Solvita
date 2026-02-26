#!/usr/bin/env python3
"""
scripts/train_hacker.py — 离线训练 Hacker Memory

用途：
    从 solvita_train_tanh.jsonl 批量读取题目，编译 incorrect_solution（buggy 代码），
    让 LLM 用 HACK 种子库生成对抗性输入攻击该 buggy 代码，将奖励信号写入 HACK SQLite。

用法：
    python scripts/train_hacker.py \\
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.llm import UnifiedLLMClient
from src.memory import MemoryClient, MemoryNamespace, Observation
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits
from src.utils.json_utils import parse_json_response


MAX_HACK_RETRIES = 3


# ─────────────────────────────────────────────────────────────
# 构建 Hacker Prompt（与 hack_test.py 中一致）
# ─────────────────────────────────────────────────────────────

def build_hacker_prompt(description: str, code: str, memory_advice: str, validator_feedback: str = "") -> str:
    advice_section = f"\n=== HACKER STRATEGY ADVICE ===\n{memory_advice}\n==============================\n" if memory_advice else ""
    feedback_section = (
        f"\n=== PREVIOUS ATTEMPT REJECTED ===\n{validator_feedback}\nGenerate DIFFERENT inputs.\n=================================\n"
        if validator_feedback else ""
    )
    return f"""You are a competitive programming hacker. Find inputs that break the buggy solution below.

Problem:
{description}
{advice_section}{feedback_section}
Buggy Solution:
```cpp
{code}
```

Generate 1-5 adversarial test inputs that trigger bugs in this code.

Return ONLY valid JSON:
{{
    "analysis": "<what bugs you found>",
    "hack_tests": [
        {{"input": "<complete stdin string with newlines>"}}
    ]
}}
"""


# ─────────────────────────────────────────────────────────────
# 单道题 Hack 训练（内部重试）
# ─────────────────────────────────────────────────────────────

def train_one_hacker(item: dict, llm: "UnifiedLLMClient", config: dict, trial_idx: int) -> dict:
    problem_id = item.get("id", f"item_{trial_idx}")
    description = item.get("description", "")
    incorrect_solutions = item.get("incorrect_solution", [])
    correct_solutions = item.get("correct_solution", [])

    if not description or not incorrect_solutions:
        return {"id": problem_id, "skipped": True, "reason": "no description or incorrect_solution"}

    buggy_code = incorrect_solutions[0].get("code", "")
    if not buggy_code:
        return {"id": problem_id, "skipped": True, "reason": "empty buggy code"}

    # 初始化 Memory Client
    memory = MemoryClient(
        namespace=MemoryNamespace.HACK,
        config=config,
        problem_desc=description,
    )

    advice, item_ids = memory.get_injection(
        fsm_state="HACK_GEN",
        failure_type=None,
        attempt_count=trial_idx,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # 1. 编译 buggy_solution
        buggy_src = tmp / "buggy.cpp"
        buggy_exe = tmp / "buggy"
        buggy_src.write_text(buggy_code, encoding="utf-8")
        ok, _ = compile_cpp(buggy_src, buggy_exe)

        if not ok:
            logger.warning(f"[{problem_id}] buggy_solution 编译失败，跳过")
            return {"id": problem_id, "skipped": True, "reason": "buggy_compile_failed"}

        # 2. 编译 correct_solution（用于差异对拍）
        correct_exe = None
        if correct_solutions:
            correct_src = tmp / "correct.cpp"
            correct_exe_path = tmp / "correct"
            correct_src.write_text(correct_solutions[0].get("code", ""), encoding="utf-8")
            c_ok, _ = compile_cpp(correct_src, correct_exe_path)
            if c_ok:
                correct_exe = correct_exe_path

        # 3. 内循环：LLM → 生成 hack 输入 → 对跑 → 计算 reward
        all_rejected = True
        hack_success = False
        validator_feedback = ""

        for attempt in range(1, MAX_HACK_RETRIES + 1):
            prompt = build_hacker_prompt(description, buggy_code, advice, validator_feedback)
            response = llm.generate(prompt)

            try:
                data = parse_json_response(response)
                hack_tests = data.get("hack_tests", [])
                logger.debug(f"[{problem_id}] 第{attempt}次：生成 {len(hack_tests)} 个 hack 输入")
            except Exception:
                logger.warning(f"[{problem_id}] 第{attempt}次：LLM 解析失败")
                continue

            valid_inputs = []
            rejection_reasons = []

            for i, test in enumerate(hack_tests):
                inp = test.get("input", "")
                if not inp.strip():
                    rejection_reasons.append(f"Input {i}: empty")
                    continue
                # 基础格式检查（无 validator exe 时）
                valid_inputs.append(inp)

            if not valid_inputs:
                validator_feedback = "\n".join(rejection_reasons) or "All inputs were empty."
                continue

            all_rejected = False

            # 4. 在 buggy_exe 上运行，看是否触发 Bug
            for inp in valid_inputs:
                b_code, b_out, b_err = run_program(buggy_exe, inp, ExecutionLimits.default_run())

                if b_code != 0:
                    # RE
                    hack_success = True
                    logger.info(f"[{problem_id}] 触发 RE！")
                    break

                # 如果有 correct_exe，做差异对拍
                if correct_exe:
                    c_code, c_out, _ = run_program(correct_exe, inp, ExecutionLimits.default_run())
                    if c_code == 0 and b_out.strip() != c_out.strip():
                        hack_success = True
                        logger.info(f"[{problem_id}] 触发 WA！buggy≠correct")
                        break

            if hack_success:
                break

    # 5. 奖励计算
    if hack_success:
        reward = 1.0
    elif all_rejected:
        reward = -1.0
    else:
        reward = 0.0

    logger.info(f"[{problem_id}] Hacker reward = {reward:+.2f}")

    # 6. 写入 SQLite
    obs = Observation(
        fsm_state="HACK_SETTLE",
        attempt_count=trial_idx,
        raw_problem_desc=description,
    )
    memory.log_event(obs, item_ids, reward, iteration=trial_idx)

    return {"id": problem_id, "reward": reward, "hack_success": hack_success}


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hacker 离线训练")
    parser.add_argument("--dataset", default="<workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 道题")
    parser.add_argument("--data-dir", default="data/memory", help="SQLite 存储目录")
    parser.add_argument("--tags", nargs="*", help="只训练包含这些 tag 的题目")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 条（断点续训）")
    args = parser.parse_args()

    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": args.data_dir,
            "hack_top_k": 3,
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

    logger.info(f"开始 Hacker 离线训练: {dataset_path}")
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
                continue

            # Tag 过滤
            if args.tags:
                item_tags = set(item.get("tags", []))
                if not item_tags.intersection(set(args.tags)):
                    continue

            result = train_one_hacker(item, llm, config, trial_idx=processed)
            results.append(result)
            processed += 1

            if processed % 10 == 0:
                rewards = [r["reward"] for r in results if "reward" in r]
                successes = sum(1 for r in results if r.get("hack_success"))
                avg = sum(rewards) / len(rewards) if rewards else 0
                logger.info(f"进度: {processed} 道 | avg reward: {avg:+.3f} | hack 成功: {successes} 道")

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
