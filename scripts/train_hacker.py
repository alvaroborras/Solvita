#!/usr/bin/env python3
"""
scripts/train_hacker.py — 离线训练 Hacker Memory (Native Driver)

用途：
    从 dataset 批量读取题目，组装初始 SolvitaState，将 bug 代码注入，
    直接驱动现有的 `hack_test_node` 和 `settle_hacker_memory`。
    以此评估 Hacker 攻击策略在真实业务管线中的表现。

用法：
    python scripts/train_hacker.py \\
        --dataset <workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl \\
        --limit 200 \\
        --data-dir data/memory
"""

import argparse
import ast
import json
import shutil
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
from src.nodes.hack_test import hack_test_node
from src.nodes.hack_test import generate_hack_candidate
from src.hacker.runtime import execute_hack_candidate
from src.hacker.dataset import build_hacker_candidate_record, append_hacker_candidate_record
from src.nodes.settle_hacker_memory import settle_hacker_memory
from src.nodes.routing import hack_routing
from src.utils.cpp_execution import compile_cpp, ExecutionLimits, run_program


# ─────────────────────────────────────────────────────────────
# 单道题训练 (Driver Wrap)
# ─────────────────────────────────────────────────────────────


def _resolve_training_judges(item: dict, config: dict) -> dict:
    item_checker = item.get("checker_exe")
    item_validator = item.get("validator_exe")
    if item_checker or item_validator:
        return {
            "judge_mode": "checker" if item_checker else "node_default",
            "checker_exe": item_checker,
            "validator_exe": item_validator,
        }

    by_problem = (config.get("offline_hacker_assets_by_problem_id", {}) or {}).get(item.get("id"), {})
    if by_problem.get("checker_exe") or by_problem.get("validator_exe"):
        return {
            "judge_mode": "checker" if by_problem.get("checker_exe") else "node_default",
            "checker_exe": by_problem.get("checker_exe"),
            "validator_exe": by_problem.get("validator_exe"),
        }

    if item.get("correct_solution"):
        return {
            "judge_mode": "correct_runner",
            "checker_exe": None,
            "validator_exe": None,
        }

    return {
        "judge_mode": "node_default",
        "checker_exe": None,
        "validator_exe": None,
    }


def _prepare_correct_runner(correct_solutions: list, tmpdir: Path):
    for idx, sol in enumerate(correct_solutions):
        code = sol.get("code", "") if isinstance(sol, dict) else str(sol)
        if not code.strip():
            continue

        cpp_src = tmpdir / f"correct_{idx}.cpp"
        cpp_exe = tmpdir / f"correct_{idx}"
        cpp_src.write_text(code, encoding="utf-8")
        ok, _ = compile_cpp(cpp_src, cpp_exe)
        if ok:
            return ("cpp", cpp_exe)

        try:
            ast.parse(code)
            py_src = tmpdir / f"correct_{idx}.py"
            py_src.write_text(code, encoding="utf-8")
            return ("python", py_src)
        except SyntaxError:
            continue

    return None


def _run_correct_runner(runner, inp: str):
    kind, path = runner
    limits = ExecutionLimits.default_run()
    if kind == "cpp":
        rc, stdout, _ = run_program(path, inp, limits=limits)
        return rc, stdout

    result = subprocess.run(
        ["python3", str(path)],
        input=inp,
        capture_output=True,
        text=True,
        timeout=limits.wall_seconds or 10,
    )
    return result.returncode, result.stdout


def _build_round_state_delta(state: dict, candidate: dict, executed: dict, expected_output: str = "") -> dict:
    failures = executed["hack_failures"]
    sandbox_verdicts = executed["sandbox_verdicts"]
    compile_failures = candidate["compile_failures"] + executed.get("compile_failures", 0)
    hacker_reward = 0.0

    tests_data = state.get("tests", {})
    updated_tests = dict(tests_data)
    if failures:
        generated_tests = tests_data.get("generated_tests", [])
        updated_tests["generated_tests"] = generated_tests + [{
            "input": candidate["generated_input"],
            "expected_output": expected_output,
            "type": "hack",
        }]
        updated_tests["total_tests"] = len(updated_tests["generated_tests"])

    primary_failure_type = failures[0].get("type", "NONE") if failures else "NONE"

    return {
        "hack_round": candidate["hack_round"],
        "hack_passed": not failures,
        "hack_failures": failures,
        "hacker_reward": hacker_reward,
        "hacker_memory_item_ids": candidate["hacker_memory_item_ids"],
        "hack_result": "BREAK" if failures else "SAFE",
        "generator_route_used": candidate["generator_route_used"],
        "hack_failure_type": primary_failure_type,
        "generator_failure_kind": candidate["generator_failure_kind"],
        "generator_failure_reason": candidate["generator_failure_reason"],
        "analyst_report": candidate["analyst_report"],
        "validator_rejection_reasons": candidate["validator_rejection_reasons"],
        "sandbox_verdicts": sandbox_verdicts,
        "compile_failures": compile_failures,
        "tests": updated_tests,
        "execution_log": candidate["execution_log"],
    }


def _run_hack_round_with_judge(state: dict, judge_setup: dict, correct_runner=None) -> dict:
    candidate = generate_hack_candidate(state)
    if candidate["generator_route_used"] == "failed" or not candidate["generated_input"]:
        return {
            "hack_round": candidate["hack_round"],
            "hack_passed": True,
            "hacker_reward": -1.0,
            "hacker_memory_item_ids": candidate["hacker_memory_item_ids"],
            "hack_failures": [],
            "hack_result": "GEN_FAILED",
            "generator_route_used": candidate["generator_route_used"],
            "hack_failure_type": "NONE",
            "generator_failure_kind": candidate["generator_failure_kind"],
            "generator_failure_reason": candidate["generator_failure_reason"],
            "analyst_report": candidate["analyst_report"],
            "execution_log": candidate["execution_log"],
            "validator_rejection_reasons": candidate["validator_rejection_reasons"],
        }

    expected_output = ""
    if judge_setup["judge_mode"] == "correct_runner" and correct_runner is not None:
        rc, out = _run_correct_runner(correct_runner, candidate["generated_input"])
        if rc == 0:
            expected_output = out if out.endswith("\n") else out + "\n"

    checker_exe = judge_setup["checker_exe"]
    executed = execute_hack_candidate(
        exe_path=Path(state["solution"]["executable_path"]),
        generated_input=candidate["generated_input"],
        expected_output=expected_output,
        checker_exe=Path(checker_exe) if checker_exe else None,
    )
    return _build_round_state_delta(state, candidate, executed, expected_output=expected_output)


def _load_checkpoint(checkpoint_path: Path, signature: dict) -> dict:
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                chk = json.load(f)
            if chk.get("signature") == signature:
                return chk
        except Exception:
            pass
    return {
        "signature": signature,
        "settled_ids": [],
        "error_ids": [],
        "last_updated": "",
        "stopped_reason": None,
    }


def _save_checkpoint(checkpoint_path: Path, checkpoint: dict):
    checkpoint["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp_path = checkpoint_path.with_suffix(".json.tmp")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)
    tmp_path.replace(checkpoint_path)


def _snapshot_memory_state(
    *,
    data_dir: Path,
    snapshot_dir: Path,
    step: int,
    signature: dict,
    checkpoint: dict,
    checkpoint_path: Path,
    candidate_records_path: str | None,
):
    snapshot_root = snapshot_dir / f"step_{step:06d}"
    if snapshot_root.exists():
        return snapshot_root

    snapshot_root.mkdir(parents=True, exist_ok=True)
    memory_snapshot_dir = snapshot_root / "memory"
    if data_dir.exists():
        shutil.copytree(data_dir, memory_snapshot_dir, dirs_exist_ok=True)
    else:
        memory_snapshot_dir.mkdir(parents=True, exist_ok=True)

    if checkpoint_path.exists():
        shutil.copy2(checkpoint_path, snapshot_root / checkpoint_path.name)

    copied_candidate_records = None
    if candidate_records_path:
        candidate_path = Path(candidate_records_path)
        if candidate_path.exists():
            copied_candidate_records = snapshot_root / candidate_path.name
            shutil.copy2(candidate_path, copied_candidate_records)

    snapshot_meta = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "step": step,
        "settled_count": len(checkpoint.get("settled_ids", [])),
        "error_count": len(checkpoint.get("error_ids", [])),
        "signature": signature,
        "source_memory_dir": str(data_dir),
        "source_checkpoint_path": str(checkpoint_path),
        "source_candidate_records_path": candidate_records_path,
        "copied_candidate_records": str(copied_candidate_records) if copied_candidate_records else None,
    }
    with (snapshot_root / "snapshot_meta.json").open("w", encoding="utf-8") as handle:
        json.dump(snapshot_meta, handle, indent=2, ensure_ascii=False)
    return snapshot_root


def _maybe_snapshot_memory(
    *,
    data_dir: Path,
    snapshot_dir: Path | None,
    snapshot_every: int,
    signature: dict,
    checkpoint: dict,
    checkpoint_path: Path,
    candidate_records_path: str | None,
):
    if snapshot_every <= 0 or snapshot_dir is None:
        return None

    settled_count = len(checkpoint.get("settled_ids", []))
    if settled_count == 0 or settled_count % snapshot_every != 0:
        return None

    return _snapshot_memory_state(
        data_dir=data_dir,
        snapshot_dir=snapshot_dir,
        step=settled_count,
        signature=signature,
        checkpoint=checkpoint,
        checkpoint_path=checkpoint_path,
        candidate_records_path=candidate_records_path,
    )


def _worker_attack(item: dict, config: dict, trial_idx: int) -> dict:
    from src.llm.unified_client import UnifiedLLMClient, set_default_client

    llm = UnifiedLLMClient(config)
    set_default_client(llm)
    return _run_hacker_training_state(item, config, trial_idx)


def _settle_memory(result: dict):
    if result.get("fatal") or result.get("skipped") or result.get("error"):
        return result

    state_snapshot = result.get("state_snapshot")
    if not state_snapshot:
        return result

    settle_delta = settle_hacker_memory(state_snapshot)
    state_snapshot.update(settle_delta)
    result["state_snapshot"] = state_snapshot
    result["reward"] = state_snapshot.get("hacker_reward", 0.0)

    candidate_path = state_snapshot.get("config", {}).get("hacker_candidate_records_path")
    if candidate_path:
        record = build_hacker_candidate_record(
            problem_id=result.get("id", ""),
            route_used=state_snapshot.get("generator_route_used", ""),
            hack_result=state_snapshot.get("hack_result", ""),
            failure_type=state_snapshot.get("hack_failure_type", ""),
            generator_failure_kind=state_snapshot.get("generator_failure_kind", ""),
            reward=result["reward"],
            validity_passed=bool(state_snapshot.get("sandbox_verdicts", [])),
            buggy_distinguished=(state_snapshot.get("hack_result") == "BREAK"),
            compile_failures=state_snapshot.get("compile_failures", 0),
        )
        append_hacker_candidate_record(Path(candidate_path), record)

    return result


def _run_hacker_training_state(item: dict, config: dict, trial_idx: int) -> dict:
    problem_id = item.get("id", f"item_{trial_idx}")
    description = item.get("description", "")
    incorrect_solutions = item.get("incorrect_solution", [])
    public_tests = item.get("test_case") or []  # Fix 1: 用真实样例替换假数据

    if not description or not incorrect_solutions:
        return {"id": problem_id, "skipped": True, "reason": "no description or incorrect_solution"}

    buggy_code = incorrect_solutions[0].get("code", "")
    if not buggy_code:
        return {"id": problem_id, "skipped": True, "reason": "empty buggy code"}

    # 1. 伪造初始 State
    # 这里要模拟成：TestGen 已经成功跑完了，并且 CodeGen 写出了一个 buggy 的实现。
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
    judge_setup = _resolve_training_judges(item, config)
    
    # 强制注入有 bug 的代码作为当前系统的 Solution
    state["solution"]["code"] = buggy_code
    
    # 假设此时是 hack 阶段的第 1 轮
    state["hack_round"] = 0
    state["hack_failures"] = []
    
    # T5: Ensure dummy executable_path is populated via compile step
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "buggy.cpp"
        exe_path = Path(tmpdir) / "buggy.exe"
        src_path.write_text(buggy_code, encoding="utf-8")
        
        # 1.5 编译 buggy code
        compiled, msg = compile_cpp(src_path, exe_path, limits=ExecutionLimits.default_compile())
        if not compiled:
            logger.warning(f"[{problem_id}] buggy code compile failed, skipping. Error: {msg[:100]}")
            return {"id": problem_id, "skipped": True, "reason": "buggy code compile fail"}
            
        state["solution"]["executable_path"] = str(exe_path)
        state["tests"]["checker_exe"] = judge_setup["checker_exe"]
        state["tests"]["validator_exe"] = judge_setup["validator_exe"]

        try:
            correct_runner = None
            if judge_setup["judge_mode"] == "correct_runner":
                correct_runner = _prepare_correct_runner(item.get("correct_solution", []) or [], Path(tmpdir))

            # 2. 调用 Hack 节点；SAFE 路径需要遵从线上子图的回合结束规则
            while True:
                logger.info(f"[{problem_id}] Entering hack_test_node...")
                if judge_setup["judge_mode"] == "node_default":
                    new_state_delta = hack_test_node(state)
                else:
                    new_state_delta = _run_hack_round_with_judge(state, judge_setup, correct_runner=correct_runner)
                state.update(new_state_delta)
                if hack_routing(state) != "hack_again":
                    break
            
            # 3. 提取运行后状态
            hack_passed = state.get("hack_passed", True)
            hacker_ids = state.get("hacker_memory_item_ids", [])

            return {
                "id": problem_id, 
                "hack_success": not hack_passed, 
                "hacker_ids": hacker_ids,
                "state_snapshot": state,
            }

        except Exception as e:
            logger.error(f"[{problem_id}] Pipeline exception: {e}")
            return {"id": problem_id, "reward": -1.0, "error": str(e)}


def train_one_hacker(item: dict, config: dict, trial_idx: int) -> dict:
    result = _run_hacker_training_state(item, config, trial_idx)
    logger.info(f"[{result.get('id', f'item_{trial_idx}')}] Settle via settle_hacker_memory...")
    return _settle_memory(result)


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from tqdm import tqdm

    parser = argparse.ArgumentParser(description="Hacker 对抗攻击离线训练 (Native Node Wrappers)")
    parser.add_argument("--dataset", default="<workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 道题")
    parser.add_argument("--data-dir", default="data/memory", help="SQLite 存储目录")
    parser.add_argument("--tags", nargs="*", help="只训练包含这些 tag 的题目")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 条")
    parser.add_argument("--workers", type=int, default=1, help="并行 worker 数 (默认 1 = 单线程)")
    parser.add_argument("--checkpoint-dir", default=None, help="断点文件目录 (默认同 data-dir)")
    parser.add_argument("--max-consecutive-errors", type=int, default=5, help="连续多少道题发生普通错误时触发快停")
    parser.add_argument(
        "--hacker-candidate-records-path",
        default=None,
        help="可选的 candidate-level JSONL 输出路径",
    )
    parser.add_argument(
        "--memory-snapshot-every",
        type=int,
        default=500,
        help="每结算多少题快照一次 memory；<=0 表示关闭",
    )
    parser.add_argument(
        "--memory-snapshot-dir",
        default=None,
        help="memory 快照输出目录 (默认在 data-dir 同级目录下创建 memory_snapshots)",
    )
    args = parser.parse_args()

    if args.checkpoint_dir:
        Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)
    snapshot_dir = None
    if args.memory_snapshot_every > 0:
        snapshot_dir = Path(args.memory_snapshot_dir) if args.memory_snapshot_dir else Path(args.data_dir).parent / "memory_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": args.data_dir,
            "hack_top_k": 3,
        },
        "hacker_candidate_records_path": args.hacker_candidate_records_path,
    }

    signature = {
        "dataset": str(Path(args.dataset).resolve()),
        "skip": args.skip,
        "limit": args.limit,
        "tags": sorted(args.tags) if args.tags else None,
    }

    checkpoint_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else Path(args.data_dir)
    checkpoint_path = checkpoint_dir / "hacker_checkpoint.json"
    chk = _load_checkpoint(checkpoint_path, signature)
    settled_ids = set(chk["settled_ids"])
    error_ids = set(chk["error_ids"])
    already_done_ids = settled_ids | error_ids

    # 提前初始化默认 LLM client 放全局
    from src.llm.unified_client import UnifiedLLMClient, set_default_client
    llm = UnifiedLLMClient(config)
    set_default_client(llm)

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"数据集不存在: {dataset_path}")
        sys.exit(1)

    items_to_process = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line_idx, line in enumerate(f):
            if line_idx < args.skip:
                continue
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            if args.tags:
                item_tags = set(item.get("tags", []))
                if not item_tags.intersection(set(args.tags)):
                    continue

            problem_id = item.get("id")
            if problem_id not in already_done_ids:
                items_to_process.append(item)

            if args.limit and (len(items_to_process) + len(already_done_ids)) >= args.limit:
                break

    total_in_scope = len(items_to_process) + len(already_done_ids)
    logger.info(f"开始 Hacker 离线训练 (Native Nodes Driver): {dataset_path}")
    logger.info(f"  范围: skip={args.skip}, limit={args.limit or 'ALL'}, 本次需运行={len(items_to_process)} 道 (已跳过={len(already_done_ids)})")
    logger.info(f"  并行: workers={args.workers}")

    pbar = tqdm(total=total_in_scope, initial=len(already_done_ids), desc="Hacker Training", ncols=100)
    fatal_occurred = False
    consecutive_errors = 0
    results = []

    def handle_result(result):
        nonlocal chk, consecutive_errors, fatal_occurred
        problem_id = result.get("id")
        settled_added = False

        if result.get("fatal"):
            fatal_occurred = True
            chk["stopped_reason"] = result.get("error")
            _save_checkpoint(checkpoint_path, chk)
            return
        elif result.get("error"):
            consecutive_errors += 1
            if problem_id and problem_id not in chk["error_ids"]:
                chk["error_ids"].append(problem_id)
            if consecutive_errors >= args.max_consecutive_errors:
                fatal_occurred = True
                chk["stopped_reason"] = f"consecutive errors >= {args.max_consecutive_errors}"
                _save_checkpoint(checkpoint_path, chk)
                return
        else:
            consecutive_errors = 0
            _settle_memory(result)
            if problem_id and problem_id not in chk["settled_ids"]:
                chk["settled_ids"].append(problem_id)
                settled_added = True

        _save_checkpoint(checkpoint_path, chk)
        if settled_added:
            _maybe_snapshot_memory(
                data_dir=Path(args.data_dir),
                snapshot_dir=snapshot_dir,
                snapshot_every=args.memory_snapshot_every,
                signature=signature,
                checkpoint=chk,
                checkpoint_path=checkpoint_path,
                candidate_records_path=args.hacker_candidate_records_path,
            )
        results.append(result)
        pbar.update(1)

    if args.workers <= 1:
        for idx, item in enumerate(items_to_process):
            if fatal_occurred:
                break
            result = _run_hacker_training_state(item, config, idx)
            handle_result(result)
    else:
        logger.info(f"启动 {args.workers} 个 worker 进程...")
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_idx = {}
            for idx, item in enumerate(items_to_process):
                future = executor.submit(_worker_attack, item, config, idx)
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                if fatal_occurred:
                    continue
                idx = future_to_idx[future]
                try:
                    result = future.result()
                except Exception as e:
                    problem_id = items_to_process[idx].get("id", f"item_{idx}")
                    result = {"id": problem_id, "reward": -1.0, "error": str(e)}
                handle_result(result)
                if fatal_occurred:
                    executor.shutdown(wait=False, cancel_futures=True)

    pbar.close()

    processed = len(chk["settled_ids"]) + len(chk["error_ids"])
    rewards = [r["reward"] for r in results if "reward" in r]
    successes = sum(1 for r in results if r.get("hack_success"))
    logger.info("=" * 50)
    logger.info(f"训练完成: {processed} 道题")
    logger.info(f"Hack 成功率: {successes}/{processed} ({successes/processed*100:.1f}%)" if processed else "")
    logger.info(f"平均 reward: {sum(rewards)/len(rewards):+.3f}" if rewards else "无有效结果")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
