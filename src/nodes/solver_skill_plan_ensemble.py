"""Multi-branch skill plan + CodeGen/Hacker tail, then merge the best branch into main state."""

from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from loguru import logger

from src.llm.token_usage import TOKEN_USAGE_ACCUMULATOR_KEY, ensure_token_usage_accumulator
from src.nodes.best_solution import is_better_ensemble_branch
from src.nodes.solver_skill_plan import run_skill_plan_once
from src.utils.problem_utils import extract_problem_code

# Must match ``src.graph.workflow`` (ensemble case log folder).
ENSEMBLE_CASE_LOG_DIR_KEY = "_ensemble_case_log_dir"
ENSEMBLE_PRE_LOG_SINK_KEY = "_ensemble_pre_log_sink_id"

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

_compiled_tail = None


def _get_codegen_hacker_tail():
    global _compiled_tail
    if _compiled_tail is None:
        from src.graph.workflow import compile_codegen_hacker_tail

        _compiled_tail = compile_codegen_hacker_tail()
    return _compiled_tail


def _sanitize_log_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(value))
    return cleaned.strip("._") or "unknown"


def _resolve_branch_log_file(base_state: Dict[str, Any], branch_id: int) -> Path | None:
    """
    Prefer ``config._ensemble_case_log_dir`` (one folder per problem from ``run_workflow``)::

        {case_dir}/branch_{id:02d}.log

    Otherwise legacy layout::

        {root}/logs/{branch_log_subdir}/{stem}_b{id}.log
    """
    cfg = base_state.get("config") or {}
    cdir = cfg.get(ENSEMBLE_CASE_LOG_DIR_KEY)
    if isinstance(cdir, str) and cdir.strip():
        p = Path(cdir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p / f"branch_{int(branch_id):02d}.log"

    sn = cfg.get("solver_network") or {}
    ens = sn.get("ensemble_skill_plans") or {}
    if not isinstance(ens, dict):
        ens = {}

    root = cfg.get("benchmark_output_dir")
    if not (isinstance(root, str) and root.strip()):
        bl = ens.get("branch_log_dir")
        root = bl if isinstance(bl, str) and bl.strip() else ""
    if not str(root).strip():
        return None

    sub = str(ens.get("branch_log_subdir") or "solvita_ensemble").strip().strip("/\\") or "solvita_ensemble"
    rp = base_state.get("raw_problem") or {}
    pid = str(rp.get("problem_id") or extract_problem_code(rp) or "unknown")
    stem = _sanitize_log_stem(pid)
    log_dir = Path(str(root)).expanduser().resolve() / "logs" / sub
    return log_dir / f"{stem}_b{int(branch_id)}.log"


def _temperature_deltas(ens: Dict[str, Any]) -> List[float]:
    div = ens.get("diversity") or {}
    raw = div.get("temperature_delta") if isinstance(div, dict) else None
    if isinstance(raw, list) and raw:
        out: List[float] = []
        for x in raw:
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                out.append(0.0)
        return out
    return [0.0]


def _prepare_branch_state(base: Dict[str, Any], branch_id: int, deltas: List[float]) -> Dict[str, Any]:
    s: Dict[str, Any] = copy.deepcopy(base)
    cfg = copy.deepcopy(s.get("config") or {})
    sn = dict(cfg.get("solver_network") or {})
    d = float(deltas[branch_id % len(deltas)])
    sn["temperature"] = float(sn.get("temperature", 1.0)) + d
    sn["skill_selection_temperature"] = float(sn.get("skill_selection_temperature", 0.2)) + d
    sn["ensemble_branch_id"] = int(branch_id)
    cfg["solver_network"] = sn
    s["config"] = cfg

    s["iteration"] = 0
    s["hack_round"] = 0
    s["hack_passed"] = False
    s["status"] = "pending"
    s["messages"] = []
    s["solver_network_oneshot_spent"] = False
    s["has_entered_hack_phase"] = False
    s["best_solution"] = {}
    s["best_tests"] = {}
    s["best_phase"] = "test"
    s["hack_failures"] = []
    s["hacker_reward"] = 0.0
    s["hack_result"] = ""
    s["generator_route_used"] = ""
    s["hack_failure_type"] = ""
    s["generator_failure_kind"] = ""
    s["generator_failure_reason"] = ""
    s["analyst_report"] = {}
    s["validator_rejection_reasons"] = []
    return s


def _apply_skill_plan_to_state(state_b: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    st = dict(state_b)
    pl = dict(st.get("plan") or {})
    pl.update(patch.get("plan") or {})
    st["plan"] = pl
    st["llm_calls"] = int(st.get("llm_calls", 0) or 0) + int(patch.get("llm_calls", 0) or 0)
    el = list(st.get("execution_log") or [])
    el.extend(patch.get("execution_log") or [])
    st["execution_log"] = el
    return st


def _branch_outcome_meta(
    branch_id: int, final: Dict[str, Any], elapsed_s: float
) -> Dict[str, Any]:
    tests = final.get("tests") or {}
    return {
        "pass_rate": float(tests.get("pass_rate", 0.0) or 0.0),
        "passed_tests": int(tests.get("passed_tests", 0) or 0),
        "total_tests": int(tests.get("total_tests", 0) or 0),
        "branch_elapsed_s": float(elapsed_s),
        "branch_index": int(branch_id),
    }


def _merge_token_accumulators(
    base_cfg: Dict[str, Any], final_cfgs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    base = copy.deepcopy(base_cfg)
    ensure_token_usage_accumulator(base)
    acc0 = dict(base.get(TOKEN_USAGE_ACCUMULATOR_KEY) or {})
    merged = dict(acc0)
    for fc in final_cfgs:
        c = copy.deepcopy(fc or {})
        ensure_token_usage_accumulator(c)
        a = c.get(TOKEN_USAGE_ACCUMULATOR_KEY) or {}
        merged["prompt_tokens"] = int(merged.get("prompt_tokens", 0) or 0) + max(
            0, int(a.get("prompt_tokens", 0) or 0) - int(acc0.get("prompt_tokens", 0) or 0)
        )
        merged["completion_tokens"] = int(merged.get("completion_tokens", 0) or 0) + max(
            0, int(a.get("completion_tokens", 0) or 0) - int(acc0.get("completion_tokens", 0) or 0)
        )
        merged["llm_calls"] = int(merged.get("llm_calls", 0) or 0) + max(
            0, int(a.get("llm_calls", 0) or 0) - int(acc0.get("llm_calls", 0) or 0)
        )
        sc = merged.setdefault("source_counts", {"api": 0, "estimated": 0, "mixed": 0})
        sc0 = acc0.get("source_counts") or {}
        sa = a.get("source_counts") or {}
        for k in ("api", "estimated", "mixed"):
            sc[k] = int(sc.get(k, 0) or 0) + max(
                0, int(sa.get(k, 0) or 0) - int(sc0.get(k, 0) or 0)
            )
    base[TOKEN_USAGE_ACCUMULATOR_KEY] = merged
    return base


def _run_one_branch(
    base: Dict[str, Any],
    branch_id: int,
    deltas: List[float],
    tail_recursion_limit: int,
) -> Tuple[int, Dict[str, Any], float, Dict[str, Any], str]:
    log_file = _resolve_branch_log_file(base, branch_id)
    sink_id = None
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # enqueue=True: thread-safe writes when parallel ensemble branches run.
        sink_id = logger.add(
            str(log_file),
            enqueue=True,
            backtrace=True,
            diagnose=False,
        )
        logger.info("[ensemble] branch {} file log: {}", branch_id, log_file)

    try:
        state_b = _prepare_branch_state(base, branch_id, deltas)
        t0 = time.perf_counter()
        sp = run_skill_plan_once(state_b)
        state_b = _apply_skill_plan_to_state(state_b, sp)
        tail = _get_codegen_hacker_tail()
        final = tail.invoke(state_b, {"recursion_limit": int(tail_recursion_limit)})
        elapsed = time.perf_counter() - t0
        meta = _branch_outcome_meta(branch_id, final, elapsed)
        log_path_str = str(log_file) if log_file is not None else ""
        return branch_id, final, elapsed, meta, log_path_str
    finally:
        if sink_id is not None:
            logger.remove(sink_id)


def solver_skill_plan_ensemble_node(state: "SolvitaState") -> Dict[str, Any]:
    cfg_root = state.get("config") or {}
    sn = cfg_root.get("solver_network") or {}
    ens = sn.get("ensemble_skill_plans") or {}
    if not bool(sn.get("enabled")) or not (isinstance(ens, dict) and bool(ens.get("enabled"))):
        return {}

    pre_sink = cfg_root.pop(ENSEMBLE_PRE_LOG_SINK_KEY, None)
    if pre_sink is not None:
        try:
            logger.remove(pre_sink)
        except ValueError:
            pass

    count = max(1, int(ens.get("count", 3) or 1))
    parallel = bool(ens.get("parallel", True))
    max_workers = max(1, min(int(ens.get("max_parallel_workers", count) or count), count))
    tail_limit = max(50, int(ens.get("tail_recursion_limit", 600) or 600))
    deltas = _temperature_deltas(ens if isinstance(ens, dict) else {})

    base_llm = int(state.get("llm_calls", 0) or 0)
    base_cfg = copy.deepcopy(cfg_root)

    results: List[Tuple[int, Dict[str, Any], float, Dict[str, Any], str]] = []

    if parallel and count > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(_run_one_branch, state, bid, deltas, tail_limit): bid
                for bid in range(count)
            }
            for fut in as_completed(futs):
                results.append(fut.result())
    else:
        for bid in range(count):
            results.append(_run_one_branch(state, bid, deltas, tail_limit))

    results.sort(key=lambda x: x[0])
    metas = [r[3] for r in results]
    finals = [r[1] for r in results]

    winner_idx = 0
    for i in range(1, len(metas)):
        if is_better_ensemble_branch(metas[i], metas[winner_idx]):
            winner_idx = i

    winner = finals[winner_idx]
    winner_id = results[winner_idx][0]

    final_cfgs = [f.get("config") or {} for f in finals]
    merged_cfg = _merge_token_accumulators(base_cfg, final_cfgs)
    sn_m = dict(merged_cfg.get("solver_network") or {})
    sn_m.pop("ensemble_branch_id", None)
    merged_cfg["solver_network"] = sn_m
    branch_log_paths = {str(r[0]): r[4] for r in results if len(r) > 4 and r[4]}
    case_log_dir = str(merged_cfg.get(ENSEMBLE_CASE_LOG_DIR_KEY) or "")
    merged_cfg["ensemble_trace"] = {
        "case_log_dir": case_log_dir,
        "branches": [
            {
                "branch_index": r[0],
                "pass_rate": r[3]["pass_rate"],
                "passed_tests": r[3]["passed_tests"],
                "total_tests": r[3]["total_tests"],
                "elapsed_s": r[3]["branch_elapsed_s"],
                "status": r[1].get("status"),
                "log_path": r[4] if len(r) > 4 else "",
            }
            for r in results
        ],
        "winner_branch_index": winner_id,
        "branch_log_paths": branch_log_paths,
    }

    total_llm_in_branches = sum(int(f.get("llm_calls", 0) or 0) for f in finals)
    llm_delta = total_llm_in_branches - count * base_llm

    trace_lines = [
        f"Ensemble skill-plan: branches={count} winner={winner_id} "
        f"winner_pass={metas[winner_idx]['pass_rate']:.3f} "
        f"winner_elapsed_s={metas[winner_idx]['branch_elapsed_s']:.2f}"
    ]
    if branch_log_paths:
        trace_lines.append(f"Ensemble per-branch logs: {branch_log_paths}")
    if case_log_dir:
        trace_lines.append(f"Ensemble case log directory: {case_log_dir}")

    out: Dict[str, Any] = {
        "solution": copy.deepcopy(winner.get("solution") or {}),
        "tests": copy.deepcopy(winner.get("tests") or {}),
        "plan": copy.deepcopy(winner.get("plan") or {}),
        "feedback": copy.deepcopy(winner.get("feedback") or {}),
        "iteration": int(winner.get("iteration", 0) or 0),
        "status": str(winner.get("status", "pending") or "pending"),
        "hack_round": int(winner.get("hack_round", 0) or 0),
        "hack_passed": bool(winner.get("hack_passed", False)),
        "hack_failures": copy.deepcopy(winner.get("hack_failures") or []),
        "hack_result": str(winner.get("hack_result", "") or ""),
        "generator_route_used": str(winner.get("generator_route_used", "") or ""),
        "hack_failure_type": str(winner.get("hack_failure_type", "") or ""),
        "generator_failure_kind": str(winner.get("generator_failure_kind", "") or ""),
        "generator_failure_reason": str(winner.get("generator_failure_reason", "") or ""),
        "messages": list(winner.get("messages") or []),
        "current_phase": str(winner.get("current_phase", state.get("current_phase", "CODEGEN")) or "CODEGEN"),
        "solver_network_oneshot_spent": bool(winner.get("solver_network_oneshot_spent", False)),
        "best_solution": copy.deepcopy(winner.get("best_solution") or {}),
        "best_tests": copy.deepcopy(winner.get("best_tests") or {}),
        "best_phase": str(winner.get("best_phase", "test") or "test"),
        "has_entered_hack_phase": bool(winner.get("has_entered_hack_phase", False)),
        "analyst_report": copy.deepcopy(winner.get("analyst_report") or {}),
        "validator_rejection_reasons": list(winner.get("validator_rejection_reasons") or []),
        "hacker_memory_item_ids": list(winner.get("hacker_memory_item_ids") or []),
        "oracle_memory_item_ids": list(winner.get("oracle_memory_item_ids") or []),
        "config": merged_cfg,
        "llm_calls": max(0, llm_delta),
        "execution_log": trace_lines,
    }

    logger.info(
        "[solver_skill_plan_ensemble] winner branch={} pass_rate={:.3f} elapsed_s={:.2f}",
        winner_id,
        metas[winner_idx]["pass_rate"],
        metas[winner_idx]["branch_elapsed_s"],
    )

    return out
