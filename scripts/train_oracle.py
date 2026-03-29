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
from src.oracle.dataset import append_candidate_record, build_candidate_record
from src.oracle.truth import evaluate_solution_consensus


# ─────────────────────────────────────────────────────────────
# 正确解运行器解析：遍历所有 correct_solutions，取第一个能成功编译或运行的
# ─────────────────────────────────────────────────────────────

def resolve_correct_runners(correct_solutions: list, tmpdir: Path, max_runners: int = 3):
    """
    遍历 correct_solutions，返回所有可用的运行器描述:
      - ("cpp", Path)       — C++ 可执行文件
      - ("python", Path)    — Python3 脚本

    策略：对每个 solution 依次：
      1. 尝试 g++ 编译为 C++ 可执行文件
      2. 如果编译失败→ 尝试 ast.parse() 检测是否合法 Python 3
      3. 两者均失败 → 跳过该 solution

    Returns:
        List[("cpp", Path) | ("python", Path)]
    """
    runners = []
    for idx, sol in enumerate(correct_solutions):
        if len(runners) >= max_runners:
            break
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
            runners.append(("cpp", cpp_exe))
            continue

        # Strategy 2: Try Python 3 (AST parse check)
        try:
            ast.parse(code)
            py_src = tmpdir / f"correct_{idx}.py"
            py_src.write_text(code, encoding="utf-8")
            logger.debug(f"[RUNNER] Solution {idx}: identified as Python 3")
            runners.append(("python", py_src))
        except SyntaxError:
            logger.warning(f"[RUNNER] Solution {idx}: neither C++ nor Python 3, skipping")

    return runners


def resolve_correct_runner(correct_solutions: list, tmpdir: Path, max_runners: int = 3):
    runners = resolve_correct_runners(correct_solutions, tmpdir, max_runners=max_runners)
    return runners[0] if runners else None


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


def verify_generated_tests_route_aware(tests: list, runners: list, route: str) -> bool:
    if not tests or not runners:
        return False
    cases = []
    for test in tests:
        inp = test.get("input", "")
        outputs = []
        for runner in runners:
            rc, out = _run_correct(runner, inp)
            if rc == 0:
                outputs.append({"input": inp, "output": out, "witness": None})
        if not outputs:
            return False
        result = evaluate_solution_consensus(route=route, cases=outputs, verifier=None)
        if not result["trusted"]:
            return False
    return True


def _build_candidate_audit_fields(tests: dict, reward: float) -> dict:
    certified_count = int(tests.get("certified_count", 0) or 0)
    certified_target_count = int(tests.get("certified_target_count", 0) or 0)
    cert_ratio = float(tests.get("cert_ratio", 0.0) or 0.0)
    compile_success = bool(tests.get("oracle_compile_success", False))
    public_self_check_pass = bool(tests.get("oracle_public_self_check_pass", False))
    probe_pack_pass = bool(tests.get("oracle_probe_pack_pass", False))
    artifact_kind = tests.get("accepted_artifact_kind") or ""
    ready = bool(tests.get("ready", False))
    generated_tests = tests.get("generated_tests", []) or []

    decision = "accept" if reward > 0 else "reject"
    reward_reason = ""
    failure_stage = ""
    failure_subtype = ""

    if reward > 0:
        reward_reason = "fully_certified" if cert_ratio >= 1.0 else "partial_certification"
        if cert_ratio < 1.0:
            failure_stage = "micro_test_certification"
            failure_subtype = "partial_certification"
    elif not ready or not generated_tests:
        reward_reason = "no_generated_tests"
        failure_stage = "generation"
        failure_subtype = "empty_generated_test_set"
    elif not compile_success:
        reward_reason = "solver_compile_failed"
        failure_stage = "solver_compile"
        failure_subtype = "compile_failed"
    elif not public_self_check_pass:
        reward_reason = "public_self_check_failed"
        failure_stage = "public_self_check"
        failure_subtype = "public_self_check_failed"
    elif certified_count == 0:
        reward_reason = "zero_certified_outputs"
        failure_stage = "micro_test_certification"
        failure_subtype = "empty_certification_set"
    elif not probe_pack_pass:
        reward_reason = "probe_pack_failed"
        failure_stage = "micro_test_certification"
        failure_subtype = "probe_pack_failed"
    elif not artifact_kind:
        reward_reason = "acceptance_gate_rejected"
        failure_stage = "artifact_emission"
        failure_subtype = "missing_accepted_artifact"
    else:
        reward_reason = "negative_reward"
        failure_stage = "verification"
        failure_subtype = "verification_rejected"

    return {
        "decision": decision,
        "certified_count": certified_count,
        "certified_target_count": certified_target_count,
        "cert_ratio": cert_ratio,
        "reward": reward,
        "reward_reason": reward_reason,
        "failure_stage": failure_stage,
        "failure_subtype": failure_subtype,
        "checker_fallback_used": bool(tests.get("checker_fallback_used", False)),
        "solver_attempt_count": int(tests.get("solver_attempt_count", 0) or 0),
        "selected_template_name": tests.get("selected_template_name") or "",
        "prompt_char_stats": dict(tests.get("prompt_char_stats", {}) or {}),
        "compact_retry_count": int(tests.get("compact_retry_count", 0) or 0),
    }


def _build_training_state_snapshot(
    *,
    state: dict,
    config: dict,
    trial_idx: int,
    tests: dict,
    route: str,
    oracle_ids: list,
    pass_rate: float,
) -> dict:
    return {
        "config": config,
        "iteration": trial_idx,
        "raw_problem": state.get("raw_problem", {}),
        "problem": state.get("problem", {}),
        "oracle_memory_item_ids": oracle_ids,
        "tests": {
            "pass_rate": pass_rate,
            "total_tests": tests.get("total_tests", 0),
            "test_results": tests.get("test_results", []),
            "oracle_route": route,
            "oracle_memory_decision": state.get("oracle_memory_decision"),
            "accepted_artifact_kind": tests.get("accepted_artifact_kind"),
            "certification_evidence": tests.get("certification_evidence", []),
            "verifier_provenance": tests.get("verifier_provenance"),
        },
        "oracle_event_metadata": state.get("oracle_event_metadata", {}),
        "status": state.get("status", "pending"),
    }


def _rebuild_oracle_memory_snapshot(config: dict) -> None:
    trainable_memory = config.get("trainable_memory", {}) or {}
    if str(trainable_memory.get("oracle_memory_mode", "updated") or "updated") != "updated":
        return
    if bool(trainable_memory.get("skip_oracle_memory_rebuild", False)):
        return

    snapshot_id = str(trainable_memory.get("oracle_memory_snapshot_id") or "oracle_memory_mvp_v1").strip()
    output_dir = str(trainable_memory.get("oracle_memory_output_dir") or "data/oracle_memory_models")
    data_dir = str(trainable_memory.get("data_dir") or "data/memory")
    rebuild_script = Path(__file__).with_name("rebuild_oracle_memory_db.py")

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(rebuild_script),
                "--data-dir",
                data_dir,
                "--snapshot-id",
                snapshot_id,
                "--output-dir",
                output_dir,
                "--prefix",
                snapshot_id,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Oracle memory snapshot rebuild failed: snapshot_id={}, returncode={}, stderr={}",
            snapshot_id,
            exc.returncode,
            (exc.stderr or "").strip(),
        )
        return
    except OSError as exc:
        logger.warning(
            "Oracle memory snapshot rebuild could not be launched: snapshot_id={}, error={}",
            snapshot_id,
            str(exc),
        )
        return
    logger.info(
        "Oracle memory snapshot rebuild complete: snapshot_id={}, output_dir={}",
        snapshot_id,
        output_dir,
    )
    if completed.stdout.strip():
        logger.info("Oracle memory rebuild output: {}", completed.stdout.strip())
    if completed.stderr.strip():
        logger.warning("Oracle memory rebuild stderr: {}", completed.stderr.strip())



# ─────────────────────────────────────────────────────────────
# Phase 1: Worker — 重计算（LLM + C++ 编译/对拍），可并行
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Phase 1: Worker — 重计算（LLM + C++ 编译/对拍），可并行
# ─────────────────────────────────────────────────────────────

def _worker_generate(item: dict, config: dict, trial_idx: int, tmp_dir: str = None) -> dict:
    """
    Worker function: runs generate_tests_node + verify.
    Returns a result dict with reward and state snapshot for settlement.
    This function does NOT write to the SQLite memory database.
    """
    problem_id = item.get("id", f"item_{trial_idx}")
    
    # Re-init LLM client in child process (not inherited across fork)
    from src.llm.unified_client import UnifiedLLMClient, set_default_client, FatalLLMError
    try:
        llm = UnifiedLLMClient(config)
        set_default_client(llm)
    except Exception as e:
        if type(e).__name__ == "ConfigurationError":
            return {"id": problem_id, "fatal": True, "fatal_kind": "ConfigurationError", "error": str(e)}
        raise

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
        "tags": item.get("tags", []),
        "is_multi_solution": bool(item.get("is_multi_solution", False)),
    }
    state = create_initial_state(raw_problem, config)
    state["iteration"] = trial_idx

    try:
        with tempfile.TemporaryDirectory(dir=tmp_dir) as tmpdir:
            tmp = Path(tmpdir)

            max_runners = int(config.get("oracle_max_correct_runners", 3))
            runner = resolve_correct_runner(correct_solutions, tmp, max_runners=max_runners)
            runners = resolve_correct_runners(correct_solutions, tmp, max_runners=max_runners)
            if runner is not None:
                state["training_mode"] = True
                state["training_runner"] = runner
                logger.debug(f"[{problem_id}] Training mode: correct_solution runner ready ({runner[0]})")
            else:
                logger.warning(f"[{problem_id}] No usable correct_solution — training mode disabled")

            # 这一步可能会抛出 FatalLLMError (例如 429 quota exhausted)
            new_state_delta = generate_tests_node(state)
            state.update(new_state_delta)

            tests = state.get("tests", {})
            generated_list = tests.get("generated_tests", [])
            oracle_ids = state.get("oracle_memory_item_ids", [])
            route = tests.get("oracle_route") or "exact_single_answer"

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
                    if route == "exact_single_answer":
                        reward = verify_generated_tests(generated_list, correct_solutions, tmp)
                    else:
                        reward = 1.0 if verify_generated_tests_route_aware(generated_list, runners, route) else -0.2
                else:
                    reward = round(cert_ratio * 0.9, 2)
            else:
                reward = -0.6

            audit_fields = _build_candidate_audit_fields(tests, reward)
            oracle_event_metadata = dict(state.get("oracle_event_metadata", {}))
            oracle_event_metadata.update(audit_fields)
            state["oracle_event_metadata"] = oracle_event_metadata

            candidate_record = build_candidate_record(
                problem_id=problem_id,
                trainability_class=route,
                candidate_family_pool=tests.get("candidate_family_pool", []),
                selected_family_id=tests.get("oracle_selected_family_id") or tests.get("oracle_primary_family_id") or "",
                fallback_family_id=tests.get("oracle_fallback_family_id") or "",
                compile_success=bool(tests.get("oracle_compile_success", False)),
                public_self_check_pass=bool(tests.get("oracle_public_self_check_pass", False)),
                probe_pack_pass=bool(tests.get("oracle_probe_pack_pass", False)),
                route=route,
                artifact_kind=tests.get("accepted_artifact_kind") or "",
                decision=audit_fields["decision"],
                certified_count=audit_fields["certified_count"],
                certified_target_count=audit_fields["certified_target_count"],
                cert_ratio=audit_fields["cert_ratio"],
                reward=audit_fields["reward"],
                reward_reason=audit_fields["reward_reason"],
                failure_stage=audit_fields["failure_stage"],
                failure_subtype=audit_fields["failure_subtype"],
                checker_fallback_used=audit_fields["checker_fallback_used"],
                solver_attempt_count=audit_fields["solver_attempt_count"],
                selected_template_name=audit_fields["selected_template_name"],
                prompt_char_stats=audit_fields["prompt_char_stats"],
                compact_retry_count=audit_fields["compact_retry_count"],
                verifier_provenance=tests.get("verifier_provenance"),
                cost={"llm_calls": state.get("llm_calls", 0)},
            )
            candidate_dataset_path = Path(config.get("oracle_candidate_records_path", "data/checkpoints/oracle_candidate_records.jsonl"))
            append_candidate_record(candidate_dataset_path, candidate_record)

            # Prepare state snapshot for settlement (Phase 2)
            pass_rate = max(0.0, min(1.0, (reward + 1.0) / 2.0))

            return {
                "id": problem_id,
                "reward": reward,
                "oracle_ids": oracle_ids,
                "pass_rate": pass_rate,
                "state_snapshot": _build_training_state_snapshot(
                    state=state,
                    config=config,
                    trial_idx=trial_idx,
                    tests=tests,
                    route=route,
                    oracle_ids=oracle_ids,
                    pass_rate=pass_rate,
                ),
            }

    except FatalLLMError as e:
        logger.error(f"[{problem_id}] Fatal LLM error: {e}")
        return {"id": problem_id, "fatal": True, "fatal_kind": type(e).__name__, "error": str(e)}
    except Exception as e:
        logger.error(f"[{problem_id}] Pipeline exception: {e}")
        return {"id": problem_id, "reward": -1.0, "error": str(e)}


# ─────────────────────────────────────────────────────────────
# Phase 2: Settlement — 串行写入 SQLite（主进程执行）
# ─────────────────────────────────────────────────────────────

def _settle_memory(result: dict):
    """Settle memory rewards in main process (serial, no SQLite lock risk)."""
    if result.get("fatal") or result.get("skipped") or result.get("error"):
        return
    state_snapshot = result.get("state_snapshot")
    if not state_snapshot:
        return
    try:
        update_oracle_memory_node(state_snapshot)
    except Exception as e:
        logger.error(f"[{result['id']}] Settlement exception: {e}")


# ─────────────────────────────────────────────────────────────
# 向后兼容：单线程模式 (workers=1)
# ─────────────────────────────────────────────────────────────

def train_one_oracle(item: dict, config: dict, trial_idx: int, tmp_dir: str = None) -> dict:
    """Legacy single-threaded entry: generate + settle in one call."""
    result = _worker_generate(item, config, trial_idx, tmp_dir=tmp_dir)
    if not result.get("fatal"):
        _settle_memory(result)
    return result


# ─────────────────────────────────────────────────────────────
# Checkpoint 机制
# ─────────────────────────────────────────────────────────────

def _load_checkpoint(checkpoint_path: Path, signature: dict) -> dict:
    """Load checkpoint if signature matches, else create new."""
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                chk = json.load(f)
            if chk.get("signature") == signature:
                return chk
            else:
                logger.warning("Checkpoint signature mismatch. Starting fresh.")
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}. Starting fresh.")
            
    return {
        "signature": signature,
        "settled_ids": [],
        "error_ids": [],
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stopped_reason": None
    }


def _save_checkpoint(checkpoint_path: Path, checkpoint: dict):
    """Atomically save checkpoint to disk."""
    checkpoint["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp_path = checkpoint_path.with_suffix(".json.tmp")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2, ensure_ascii=False)
        tmp_path.replace(checkpoint_path)
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def main():
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from tqdm import tqdm

    parser = argparse.ArgumentParser(description="Oracle TestGen 离线训练 (Resilience 加固版)")
    parser.add_argument("--dataset", default="<workspace>/duture/solvita/data/solvita_train/solvita_train_tanh.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 道题")
    parser.add_argument("--data-dir", default="data/memory", help="SQLite 内存存储目录")
    parser.add_argument("--tags", nargs="*", help="只训练包含这些 tag 的题目")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 条")
    parser.add_argument("--workers", type=int, default=1, help="并行 worker 数 (默认 1 = 单线程)")
    parser.add_argument("--tmp-dir", default=None, help="临时文件存放目录 (建议设在大盘路径)")
    parser.add_argument("--checkpoint-dir", default=None, help="断点文件目录 (默认同 data-dir)")
    parser.add_argument("--max-consecutive-errors", type=int, default=5, help="连续多少道题发生普通错误时触发快停")
    parser.add_argument("--max-correct-runners", type=int, default=3, help="每题最多保留多少个可运行 correct_solution 作为辅助校验")
    parser.add_argument(
        "--oracle-memory-mode",
        choices=["off", "frozen", "updated"],
        default="updated",
        help="Oracle memory runtime/rebuild mode",
    )
    parser.add_argument(
        "--oracle-memory-snapshot-id",
        default="oracle_memory_mvp_v1",
        help="Snapshot id used for Oracle memory runtime and rebuild output",
    )
    parser.add_argument(
        "--skip-oracle-memory-rebuild",
        action="store_true",
        help="Skip rebuilding the Oracle memory DB snapshot after training",
    )
    parser.add_argument(
        "--oracle-memory-output-dir",
        default="data/oracle_memory_models",
        help="Output directory for rebuilt Oracle memory artifacts",
    )
    args = parser.parse_args()

    if args.tmp_dir:
        Path(args.tmp_dir).mkdir(parents=True, exist_ok=True)
    if args.checkpoint_dir:
        Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    config = {
        "trainable_memory": {
            "enabled": True,
            "data_dir": args.data_dir,
            "oracle_top_k": 3,
            "oracle_memory_mode": args.oracle_memory_mode,
            "oracle_memory_snapshot_id": args.oracle_memory_snapshot_id,
            "skip_oracle_memory_rebuild": args.skip_oracle_memory_rebuild,
            "oracle_memory_output_dir": args.oracle_memory_output_dir,
        },
        "oracle_max_correct_runners": args.max_correct_runners,
    }
    
    # Checkpoint Signature
    signature = {
        "dataset": str(Path(args.dataset).resolve()),
        "skip": args.skip,
        "limit": args.limit,
        "tags": sorted(args.tags) if args.tags else None
    }
    
    checkpoint_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else Path(args.data_dir)
    checkpoint_path = checkpoint_dir / "oracle_checkpoint.json"
    
    chk = _load_checkpoint(checkpoint_path, signature)
    settled_ids = set(chk["settled_ids"])
    error_ids = set(chk["error_ids"])
    already_done_ids = settled_ids | error_ids

    # ── 预加载并过滤符合条件的题目 ──────────────────────────
    items_to_process = []
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error(f"数据集不存在: {dataset_path}")
        sys.exit(1)

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
    logger.info(f"开始 Oracle 离线训练: {dataset_path}")
    logger.info(f"  范围: skip={args.skip}, limit={args.limit or 'ALL'}, 本次需运行={len(items_to_process)} 道 (已跳过={len(already_done_ids)})")
    logger.info(f"  并行: workers={args.workers}")

    # 主进程初始化 LLM client
    from src.llm.unified_client import UnifiedLLMClient, set_default_client
    try:
        llm = UnifiedLLMClient(config)
        set_default_client(llm)
    except UnifiedLLMClient.ConfigurationError as e:
        logger.error(f"Failed to initialize LLM client: {e}")
        sys.exit(1)

    pbar = tqdm(total=total_in_scope, initial=len(already_done_ids), desc="Oracle Training", ncols=100)

    fatal_occurred = False
    consecutive_errors = 0
    results = []

    def handle_result(result):
        nonlocal chk, consecutive_errors, fatal_occurred
        problem_id = result.get("id")
        
        if result.get("fatal"):
            # 【致命错误快停】
            fatal_occurred = True
            logger.error(f"[FATAL] 检测到全局致命错误 [{result.get('fatal_kind')}]: {result.get('error')}")
            chk["stopped_reason"] = result.get("error")
            _save_checkpoint(checkpoint_path, chk)
            return
        elif result.get("error"):
            # 【普通题目级失败】
            consecutive_errors += 1
            if problem_id and problem_id not in chk["error_ids"]:
                chk["error_ids"].append(problem_id)
            if consecutive_errors >= args.max_consecutive_errors:
                fatal_occurred = True
                logger.error(f"[FATAL] 连续 {args.max_consecutive_errors} 道题失败，疑似网络闪断或其他系统性故障，停止训练。")
                chk["stopped_reason"] = f"consecutive errors >= {args.max_consecutive_errors}"
                _save_checkpoint(checkpoint_path, chk)
                return
        else:
            # 【正常通过并结算】
            consecutive_errors = 0
            if "reward" in result:
                _settle_memory(result)
                if problem_id and problem_id not in chk["settled_ids"]:
                    chk["settled_ids"].append(problem_id)

        _save_checkpoint(checkpoint_path, chk)
        results.append(result)
        pbar.update(1)

    if args.workers <= 1:
        # ── 单线程模式 ──────────────────────────
        for idx, item in enumerate(items_to_process):
            if fatal_occurred:
                break
            result = train_one_oracle(item, config, trial_idx=idx, tmp_dir=args.tmp_dir)
            handle_result(result)
    else:
        # ── 多进程模式 ─────────────────────────────────────
        logger.info(f"启动 {args.workers} 个 worker 进程...")
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_idx = {}
            for idx, item in enumerate(items_to_process):
                future = executor.submit(_worker_generate, item, config, idx, tmp_dir=args.tmp_dir)
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                if fatal_occurred:
                    continue  # 已触发快停，无视后续任务
                
                idx = future_to_idx[future]
                try:
                    result = future.result()
                except Exception as e:
                    problem_id = items_to_process[idx].get("id", f"item_{idx}")
                    logger.error(f"[{problem_id}] Worker exception: {e}")
                    result = {"id": problem_id, "reward": -1.0, "error": str(e)}

                handle_result(result)
                
                # 在回调中如果设置了 fatal_occurred，那么立刻终止尚未调度的 future
                if fatal_occurred:
                    executor.shutdown(wait=False, cancel_futures=True)

    pbar.close()

    if fatal_occurred:
        logger.info("训练被中止。已保留的进度将会在下次安全恢复。")
    else:
        chk["stopped_reason"] = None
        _save_checkpoint(checkpoint_path, chk)
        
        rewards = [r["reward"] for r in results if "reward" in r]
        logger.info("=" * 50)
        logger.info(f"训练完毕!")
        if rewards:
            logger.info(f"本次新跑平均 reward: {sum(rewards)/len(rewards):+.3f}")
        _rebuild_oracle_memory_snapshot(config)
        logger.info("=" * 50)


if __name__ == "__main__":
    main()
