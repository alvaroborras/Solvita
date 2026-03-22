#!/usr/bin/env python3
"""
scripts/run_baseline.py — Baseline 测试 Runner

完全禁用 trainable_memory，仅使用纯 LLM pipeline 跑题目，
记录每题的结果指标，用于建立性能基线。

用法：
    # 跑 data/problem/ 下所有题目
    python scripts/run_baseline.py

    # 指定题目目录或单个 JSONL 文件
    python scripts/run_baseline.py --input data/problem/

    # 限制题目数量
    python scripts/run_baseline.py --limit 5

    # 覆盖迭代上限
    python scripts/run_baseline.py --max-iterations 3 --max-hack-rounds 2

输出：
    结果写入 --output 指定路径（默认 data/baseline_results.jsonl），
    每行一条 JSON，包含每题的完整指标。
    运行结束后打印汇总统计。
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 把项目根加入 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.graph.workflow import run_workflow


# ─────────────────────────────────────────────────────────────
# 题目加载
# ─────────────────────────────────────────────────────────────

def load_problems(input_path: Path) -> list:
    """
    从路径加载题目列表。

    支持两种格式：
    - 目录：读取目录下所有 *.json 文件，每个文件一道题
    - JSONL 文件：每行一道题
    """
    problems = []

    if input_path.is_dir():
        json_files = sorted(input_path.glob("*.json"))
        if not json_files:
            logger.error(f"目录 {input_path} 下没有找到 *.json 文件")
            return []
        for f in json_files:
            try:
                problem = json.loads(f.read_text(encoding="utf-8"))
                # 注入文件名作为 problem_id（若 _metadata 里没有的话）
                if "_metadata" not in problem:
                    problem["_metadata"] = {}
                if "problem_id" not in problem["_metadata"]:
                    problem["_metadata"]["problem_id"] = f.stem
                problems.append(problem)
            except Exception as e:
                logger.warning(f"跳过 {f.name}：{e}")

    elif input_path.suffix == ".jsonl":
        with open(input_path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    problems.append(json.loads(line))
                except Exception as e:
                    logger.warning(f"跳过第 {lineno} 行：{e}")

    else:
        logger.error(f"不支持的输入格式：{input_path}（需要目录或 .jsonl 文件）")

    return problems


def extract_problem_id(problem: dict) -> str:
    """从题目 dict 中提取一个可读的 problem_id。"""
    meta = problem.get("_metadata", {})
    for key in ("problem_id", "name", "question_id"):
        val = meta.get(key)
        if val:
            return str(val)
    # 降级：用描述的前 40 个字符
    desc = problem.get("description", "")
    return desc[:40].replace("\n", " ").strip() or "unknown"


# ─────────────────────────────────────────────────────────────
# 单题运行
# ─────────────────────────────────────────────────────────────

def run_one(problem: dict, config: dict) -> dict:
    """
    运行单道题，返回结果记录 dict。
    捕获所有异常，保证批跑不中断。
    """
    problem_id = extract_problem_id(problem)
    started_at = time.time()

    try:
        final_state = run_workflow(problem, config)
        elapsed = time.time() - started_at

        tests = final_state.get("tests", {})
        solution = final_state.get("solution", {})

        # hack_outcome 在顶层 state 里没有直接存，从 status + hack 字段推导
        hack_passed = final_state.get("hack_passed", False)
        hack_round  = final_state.get("hack_round", 0)
        hack_result = final_state.get("hack_result", "")   # "BREAK"/"SAFE"/"GEN_FAILED"/""
        gen_fail_kind = final_state.get("generator_failure_kind", "")
        gen_fail_reason = final_state.get("generator_failure_reason", "")

        # 推导 top-level hack outcome：
        #   必须先确认 status=="success"（即曾进入 hacker 阶段），
        #   否则题目在 CodeGen 阶段就结束，hack 字段全是初始值，不能推导 hack_outcome。
        #   hack_outcome_routing 只在 hacker_phase 退出后才被调用，语义与此一致。
        iteration      = final_state.get("iteration", 0)
        max_iterations = final_state.get("max_iterations", config.get("max_iterations", 5))
        status         = final_state.get("status", "unknown")

        if status != "success":
            if hack_result == "BREAK":
                hack_outcome = "hack_broken"
            else:
                # 未通过所有测试，未进入 hacker 阶段
                hack_outcome = "not_reached"
        elif not hack_passed and iteration < max_iterations:
            hack_outcome = "loop_codegen"   # hacker 找到 bug，触发回环
        else:
            hack_outcome = "final_ac"       # hacker 未攻破（SAFE/GEN_FAILED 耗尽轮次）

        return {
            "problem_id":   problem_id,
            "status":       final_state.get("status", "unknown"),
            "iteration":    iteration,
            "llm_calls":    final_state.get("llm_calls", 0),
            "pass_rate":    tests.get("pass_rate", 0.0),
            "total_tests":  tests.get("total_tests", 0),
            "passed_tests": tests.get("passed_tests", 0),
            "hack_passed":  hack_passed,
            "hack_round":   hack_round,
            "hack_result":  hack_result,
            "hack_outcome": hack_outcome,
            "gen_fail_kind": gen_fail_kind,
            "gen_fail_reason": gen_fail_reason,
            "elapsed_s":    round(elapsed, 2),
            "error":        None,
        }

    except Exception as exc:
        elapsed = time.time() - started_at
        logger.error(f"[{problem_id}] 运行异常：{exc}")
        return {
            "problem_id":   problem_id,
            "status":       "error",
            "iteration":    0,
            "llm_calls":    0,
            "pass_rate":    0.0,
            "total_tests":  0,
            "passed_tests": 0,
            "hack_passed":  False,
            "hack_round":   0,
            "hack_result":  "",
            "hack_outcome": "",
            "gen_fail_kind": "",
            "gen_fail_reason": "",
            "elapsed_s":    round(elapsed, 2),
            "error":        str(exc),
        }


# ─────────────────────────────────────────────────────────────
# Memory 文件快照 & 运行后对比
# ─────────────────────────────────────────────────────────────

def snapshot_memory_mtimes(data_dir: Path) -> dict:
    """
    记录 data_dir 下所有 .db/.json 文件的当前修改时间戳，返回快照 dict。
    在运行前调用，用于运行后与 assert_memory_unchanged() 对比。
    """
    logger.info("=" * 60)
    logger.info("Memory 文件快照（运行前基准）")
    logger.info("=" * 60)
    logger.info("config 中未设置 trainable_memory.enabled，memory 将静默禁用")
    logger.info("预期日志中会出现（每命名空间一条）：")
    logger.info("    Memory [plan] is disabled in config.")
    logger.info("    Memory [solve] is disabled in config.")
    logger.info("    Memory [hack] is disabled in config.")
    logger.info("    Memory [oracle] is disabled in config.")

    snapshot: dict = {}
    if data_dir.exists():
        for f in sorted(data_dir.rglob("*")):
            if f.is_file() and f.suffix in (".db", ".json"):
                mtime = f.stat().st_mtime
                rel = str(f.relative_to(data_dir))
                snapshot[rel] = mtime
                ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"  [before] {rel}  →  {ts}")
    else:
        logger.info(f"{data_dir} 不存在，运行前无 memory 文件")

    logger.info("=" * 60)
    return snapshot


def assert_memory_unchanged(data_dir: Path, before: dict) -> None:
    """
    运行结束后与 before 快照对比。
    若有文件被新建或 mtime 改变，打印 WARNING——表示 memory 并未真正被禁用。
    """
    logger.info("=" * 60)
    logger.info("Memory 文件对比（运行后验证）")
    logger.info("=" * 60)

    violations: list = []

    if data_dir.exists():
        after: dict = {}
        for f in sorted(data_dir.rglob("*")):
            if f.is_file() and f.suffix in (".db", ".json"):
                mtime = f.stat().st_mtime
                rel = str(f.relative_to(data_dir))
                after[rel] = mtime

        for rel, mtime_after in after.items():
            if rel not in before:
                violations.append(f"新建文件：{rel}")
            elif mtime_after != before[rel]:
                ts_before = datetime.fromtimestamp(before[rel]).strftime("%Y-%m-%d %H:%M:%S")
                ts_after  = datetime.fromtimestamp(mtime_after).strftime("%Y-%m-%d %H:%M:%S")
                violations.append(f"已修改：{rel}  ({ts_before} → {ts_after})")
    elif before:
        # 运行前有文件，运行后目录消失（不太可能，但防御性检查）
        violations.append(f"{data_dir} 运行后不存在，无法对比")

    if violations:
        logger.warning("⚠ Memory 文件发生变化，trainable_memory 可能未被正确禁用：")
        for v in violations:
            logger.warning(f"    {v}")
    else:
        logger.info("✓ Memory 文件无变化，trainable_memory 已确认禁用")

    logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────
# 汇总统计
# ─────────────────────────────────────────────────────────────

def print_summary(results: list) -> None:
    total = len(results)
    if total == 0:
        logger.info("没有题目结果可汇总。")
        return

    ac        = sum(1 for r in results if r["status"] == "success")
    errors    = sum(1 for r in results if r["status"] == "error")
    final_ac  = sum(1 for r in results if r["hack_outcome"] == "final_ac")
    avg_iter  = sum(r["iteration"] for r in results) / total
    avg_calls = sum(r["llm_calls"] for r in results) / total
    avg_rate  = sum(r["pass_rate"] for r in results) / total
    avg_time  = sum(r["elapsed_s"] for r in results) / total

    logger.info("")
    logger.info("=" * 60)
    logger.info("Baseline 汇总")
    logger.info("=" * 60)
    logger.info(f"  总题数:         {total}")
    logger.info(f"  AC 数:          {ac}  ({ac/total:.1%})")
    logger.info(f"  Final AC 数:    {final_ac}  ({final_ac/total:.1%})  [AC 且 hacker 未攻破]")
    logger.info(f"  错误数:         {errors}")
    logger.info(f"  平均迭代次数:   {avg_iter:.2f}")
    logger.info(f"  平均 LLM 调用:  {avg_calls:.1f}")
    logger.info(f"  平均 pass_rate: {avg_rate:.2%}")
    logger.info(f"  平均耗时(s):    {avg_time:.1f}")
    logger.info("=" * 60)

    # 逐题明细
    logger.info("")
    logger.info("逐题明细：")
    header = f"{'problem_id':<40} {'status':<15} {'iter':>4} {'rate':>6} {'hack':>10} {'elapsed':>8}"
    logger.info(header)
    logger.info("-" * len(header))
    for r in results:
        pid    = r["problem_id"][:39]
        status = r["status"]
        itr    = r["iteration"]
        rate   = f"{r['pass_rate']:.0%}"
        hack   = r["hack_outcome"] or r["hack_result"] or "-"
        elapsed = f"{r['elapsed_s']:.1f}s"
        logger.info(f"{pid:<40} {status:<15} {itr:>4} {rate:>6} {hack:>10} {elapsed:>8}")


# ─────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Solvita Baseline Runner — 纯 LLM pipeline，无 Memory"
    )
    parser.add_argument(
        "--input", type=str, default="data/problem",
        help="题目目录（*.json）或 JSONL 文件路径（默认：data/problem）",
    )
    parser.add_argument(
        "--output", type=str, default="data/baseline_results.jsonl",
        help="结果输出路径（默认：data/baseline_results.jsonl）",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="最多运行前 N 道题（默认：全部）",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=5,
        help="每题 CodeGen 最大迭代次数（默认：5）",
    )
    parser.add_argument(
        "--max-hack-rounds", type=int, default=3,
        help="每题 Hacker 最大轮次（默认：3）",
    )
    parser.add_argument(
        "--config-path", type=str, default="config/models.yaml",
        help="LLM 配置文件路径（默认：config/models.yaml）",
    )
    parser.add_argument(
        "--memory-dir", type=str, default="data/memory",
        help="Memory 数据目录，仅用于运行前时间戳验证（默认：data/memory）",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── config-path 存在性校验（fail-fast，防止静默回落到默认配置）──
    config_path = Path(args.config_path)
    if not config_path.exists():
        logger.error(f"配置文件不存在：{config_path}，请检查 --config-path 参数")
        sys.exit(1)

    # ── Baseline config：trainable_memory 字段完全不设置 ──────
    config = {
        "config_path":      args.config_path,   # 指向具体 yaml 文件，非目录
        "max_iterations":   args.max_iterations,
        "max_hack_rounds":  args.max_hack_rounds,
        # trainable_memory 不出现 => MemoryClient.enabled 默认 False
    }

    # ── 加载题目 ─────────────────────────────────────────────
    input_path = Path(args.input)
    problems = load_problems(input_path)
    if not problems:
        logger.error("没有可用的题目，退出。")
        sys.exit(1)

    if args.limit:
        problems = problems[: args.limit]

    logger.info(f"共加载 {len(problems)} 道题目，开始 baseline 测试")
    logger.info(f"config_path = {args.config_path}")
    logger.info(f"max_iterations = {args.max_iterations}, max_hack_rounds = {args.max_hack_rounds}")

    # ── Memory 文件快照（运行前基准）─────────────────────────
    memory_dir = Path(args.memory_dir)
    before_snapshot = snapshot_memory_mtimes(memory_dir)

    # ── 输出文件准备 ──────────────────────────────────────────
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with open(output_path, "w", encoding="utf-8") as out_fh:
        for idx, problem in enumerate(problems, 1):
            pid = extract_problem_id(problem)
            logger.info("")
            logger.info(f"[{idx}/{len(problems)}] 题目：{pid}")

            record = run_one(problem, config)
            results.append(record)

            # 实时写入，防止中途崩溃丢失结果
            out_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_fh.flush()

            logger.info(
                f"  → status={record['status']}, pass_rate={record['pass_rate']:.0%}, "
                f"iter={record['iteration']}, llm_calls={record['llm_calls']}, "
                f"hack_outcome={record['hack_outcome']}, elapsed={record['elapsed_s']}s"
            )

    # ── 汇总 ──────────────────────────────────────────────────
    print_summary(results)

    # ── Memory 文件对比（运行后验证）─────────────────────────
    assert_memory_unchanged(memory_dir, before_snapshot)

    logger.info(f"结果已写入：{output_path}")


if __name__ == "__main__":
    main()
