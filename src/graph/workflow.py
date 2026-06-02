"""LangGraph Workflow Definition for Solvita Agent

Workflow overview (Abstract → TestGen → CodeGen → Hacker + Hack→CodeGen loop)
============================================================================
Phase 0: Abstract — abstract_problem (canonical + whitelist tags + confidence)
          ↓ phase_transition_0
Phase 1: TestGen  — generate_tests
          ↓ phase_transition_1
Phase 1b: Solver plan (optional) — solver_skill_plan (when solver_network.enabled)
          builds DAG + skill selection + solver_graph_augmentation_block; skipped on Hack→CodeGen loop
          When ensemble_skill_plans.enabled: solver_skill_plan_ensemble runs N parallel/sequential
          skill-plan + CodeGen/Hacker tail invokes, merges winner, then END (no main-graph CodeGen/Hacker).
Phase 2: CodeGen  — generate_code/compile → run_tests
                    → memory settlement → status_routing
          ↓ phase_transition_2
Phase 3: Hacker   — hack_test (≤3 retry) → settle_hacker_memory
          ↓ hack_outcome_routing:
              "loop_codegen" → phase_transition_3 → back to CodeGen
              "final_ac"     → END

Iteration budget: iteration increments per codegen repair round; max_iterations stops the run.
"""

from pathlib import Path
from types import SimpleNamespace

try:
    from langgraph.graph import StateGraph, END
except ModuleNotFoundError:
    END = "END"

    class _CompiledFallbackGraph:
        def __init__(self, nodes, edges, entry_point):
            self.nodes = nodes
            self.edges = edges
            self.entry_point = entry_point

        def get_graph(self):
            return SimpleNamespace(nodes=self.nodes, edges=self.edges, entry_point=self.entry_point)

        def invoke(self, *_args, **_kwargs):
            raise ModuleNotFoundError("langgraph is required to execute workflows in this environment")

        def stream(self, *_args, **_kwargs):
            raise ModuleNotFoundError("langgraph is required to execute workflows in this environment")

    class StateGraph:
        def __init__(self, *_args, **_kwargs):
            self._nodes = {}
            self._edges = []
            self._entry_point = None

        def add_node(self, name, node):
            self._nodes[name] = node

        def set_entry_point(self, name):
            self._entry_point = name

        def add_edge(self, source, target):
            self._edges.append(
                {"source": source, "target": target, "condition": None, "label": None}
            )

        def add_conditional_edges(self, source, condition, mapping):
            condition_name = getattr(condition, "__name__", str(condition))
            for label, target in mapping.items():
                self._edges.append(
                    {
                        "source": source,
                        "target": target,
                        "condition": condition_name,
                        "label": label,
                    }
                )

        def compile(self):
            return _CompiledFallbackGraph(
                dict(self._nodes),
                list(self._edges),
                self._entry_point,
            )

import src.events as events
from src.graph.state import SolvitaState, create_initial_state
from src.utils.problem_utils import extract_problem_code
from src.nodes import (
    abstract_problem_node,
    failure_bank_lookup_node,
    pre_solve_controller_node,
    bootstrap_tests_node,
    generate_tests_node,
    solver_skill_plan_node,
    solver_skill_plan_ensemble_node,
    generate_code_node,
    compile_code_node,
    run_tests_node,
    unified_check_node,
    analyze_feedback_node,
    update_plan_memory_node,
    update_solve_memory_node,
    update_oracle_memory_node,
    update_best_solution_node,
    enter_hack_phase_node,
    restore_best_solution_node,
    hack_test_node,
    join_ready_node,
    join_wait_node,
    status_routing,
    post_codegen_routing,
    bootstrap_routing,
    plan_or_codegen_routing,
    verifier_phase_node,
    post_verify_controller_node,
    post_verify_routing,
    compilation_routing,
    hack_routing,
    hack_outcome_routing,
    join_routing,
    phase_transition_node,
)
from src.llm.token_usage import ensure_token_usage_accumulator, get_token_usage_snapshot
from src.nodes.settle_hacker_memory import settle_hacker_memory
from typing import Dict, Any
from loguru import logger

# Per-problem ensemble log folder (set by ``setup_ensemble_case_logging`` in ``run_workflow``).
ENSEMBLE_CASE_LOG_DIR_KEY = "_ensemble_case_log_dir"
ENSEMBLE_PRE_LOG_SINK_KEY = "_ensemble_pre_log_sink_id"


def _sanitize_problem_stem_for_logs(raw_problem: Dict[str, Any]) -> str:
    pid = str((raw_problem or {}).get("problem_id") or extract_problem_code(raw_problem or {}) or "unknown")
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in pid)
    return cleaned.strip("._") or "unknown"


def _ensemble_case_log_root(cfg: Dict[str, Any]) -> str | None:
    sn = cfg.get("solver_network") or {}
    ens = sn.get("ensemble_skill_plans") or {}
    root = cfg.get("benchmark_output_dir")
    if not (isinstance(root, str) and root.strip()):
        bl = ens.get("branch_log_dir") if isinstance(ens, dict) else None
        root = bl if isinstance(bl, str) and bl.strip() else ""
    return str(root).strip() or None


def _ensemble_will_use_case_logs(cfg: Dict[str, Any]) -> bool:
    sn = cfg.get("solver_network") or {}
    ens = sn.get("ensemble_skill_plans") or {}
    if not bool(sn.get("enabled")) or not isinstance(ens, dict) or not bool(ens.get("enabled")):
        return False
    return _ensemble_case_log_root(cfg) is not None


def setup_ensemble_case_logging(initial_state: Dict[str, Any]) -> None:
    """
    When ensemble is enabled and a log root exists, create one directory per problem::

        {root}/logs/ensemble_cases/{stem}/00_pre_ensemble.log

    and attach a loguru sink so Abstract→TestGen (up to ensemble) are captured.
    ``solver_skill_plan_ensemble_node`` removes this sink and writes ``branch_XX.log`` there.
    """
    cfg = initial_state.get("config") or {}
    if not _ensemble_will_use_case_logs(cfg):
        return
    root = _ensemble_case_log_root(cfg)
    assert root  # guarded by _ensemble_will_use_case_logs
    stem = _sanitize_problem_stem_for_logs(initial_state.get("raw_problem") or {})
    case_dir = Path(root).expanduser().resolve() / "logs" / "ensemble_cases" / stem
    case_dir.mkdir(parents=True, exist_ok=True)
    pre_path = case_dir / "00_pre_ensemble.log"
    sink_id = logger.add(str(pre_path), enqueue=True, backtrace=True, diagnose=False)
    cfg[ENSEMBLE_CASE_LOG_DIR_KEY] = str(case_dir)
    cfg[ENSEMBLE_PRE_LOG_SINK_KEY] = sink_id
    logger.info(
        "[ensemble_case_logs] case_dir={} pre_ensemble={}",
        case_dir,
        pre_path.name,
    )


def teardown_ensemble_pre_log_sink(config: Dict[str, Any] | None) -> None:
    """Remove pre-ensemble file sink if still registered (e.g. workflow error before ensemble)."""
    if not isinstance(config, dict):
        return
    sid = config.pop(ENSEMBLE_PRE_LOG_SINK_KEY, None)
    if sid is not None:
        try:
            logger.remove(sid)
        except ValueError:
            pass


def after_testgen_routing(state: Dict[str, Any]) -> str:
    """After TestGen: either run skill-plan ensemble (tail-only) or single-branch skill plan + main tail."""
    sn = (state.get("config") or {}).get("solver_network") or {}
    ens = sn.get("ensemble_skill_plans") or {}
    if bool(sn.get("enabled")) and isinstance(ens, dict) and bool(ens.get("enabled")):
        return "ensemble"
    return "single"


def terminal_hack_failure_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mark a terminal hacker-discovered failure after the repair budget is exhausted."""
    return {
        "status": "max_iterations",
        "execution_log": [
            "Hack discovered a bug after the repair budget was exhausted"
        ],
    }


# ============================================================
# Phase 0: Abstract Subgraph
# ============================================================
def create_abstract_subgraph():
    """Phase 0 — canonical problem + tag selection."""
    g = StateGraph(SolvitaState)
    g.add_node("abstract_problem", abstract_problem_node)
    g.set_entry_point("abstract_problem")
    g.add_edge("abstract_problem", END)
    return g.compile()


# ============================================================
# Phase 1: TestGen Subgraph
# ============================================================

def create_testgen_subgraph():
    """Phase 1 — 暴力神谕测试集生成子图"""
    g = StateGraph(SolvitaState)
    g.add_node("generate_tests", generate_tests_node)
    g.set_entry_point("generate_tests")
    g.add_edge("generate_tests", END)
    return g.compile()


# ============================================================
# Phase 2: CodeGen Subgraph
# ============================================================

def create_codegen_subgraph():
    """Phase 2 — 正向代码生成 + 内部重试子图"""
    g = StateGraph(SolvitaState)

    g.add_node("generate_code", generate_code_node)
    g.add_node("compile_code", compile_code_node)
    g.add_node("join_ready", join_ready_node)
    g.add_node("join_wait", join_wait_node)
    g.add_node("run_tests", run_tests_node)
    g.add_node("update_best_solution", update_best_solution_node)
    g.add_node("unified_check", unified_check_node)
    g.add_node("update_plan_memory", update_plan_memory_node)
    g.add_node("update_solve_memory", update_solve_memory_node)
    g.add_node("update_oracle_memory", update_oracle_memory_node)
    g.add_node("restore_best_solution", restore_best_solution_node)
    g.add_node("analyze_feedback", analyze_feedback_node)

    g.set_entry_point("generate_code")

    g.add_edge("generate_code", "compile_code")

    g.add_conditional_edges(
        "compile_code",
        compilation_routing,
        {
            "success": "join_ready",
            "failed": "analyze_feedback",
            "exhausted": END,
        },
    )

    g.add_conditional_edges(
        "join_ready",
        join_routing,
        {
            "ready": "run_tests",
            "wait": "join_wait",
        },
    )

    g.add_edge("run_tests", "update_best_solution")
    g.add_edge("update_best_solution", "unified_check")
    g.add_edge("unified_check", "update_plan_memory")
    g.add_edge("update_plan_memory", "update_solve_memory")
    g.add_edge("update_solve_memory", "update_oracle_memory")

    g.add_conditional_edges(
        "update_oracle_memory",
        status_routing,
        {
            "continue": "analyze_feedback",
            "hack": END,   # 解法通过所有测试，出 Phase 2 → 进 Phase 3
            "finish": END,  # hacker disabled -> finish after codegen success
            "end": "restore_best_solution",    # 超出迭代次数，恢复最佳解后退出
        },
    )

    g.add_edge("restore_best_solution", END)
    g.add_edge("analyze_feedback", "generate_code")

    return g.compile()


# ============================================================
# Phase 3: Hacker Subgraph
# ============================================================

def create_hacker_subgraph():
    """Phase 3 — 对抗性 Hack + 内存结算子图"""
    g = StateGraph(SolvitaState)

    g.add_node("hack_test", hack_test_node)
    g.add_node("settle_hacker_memory", settle_hacker_memory)

    g.set_entry_point("hack_test")

    g.add_conditional_edges(
        "hack_test",
        hack_routing,
        {
            "hack_again": "hack_test",          # 本轮 hack 通过，继续 hack
            "hack_failed": "settle_hacker_memory",  # hack 发现 bug，结算
            "end": "settle_hacker_memory",       # 用光 hack 轮次，结算
        },
    )

    g.add_edge("settle_hacker_memory", END)

    return g.compile()


def compile_codegen_hacker_tail():
    """
    Standalone subgraph invoked per ensemble branch: CodeGen ↔ Hacker with the same
    structure as the main orchestrator tail (from ``codegen_phase`` onward).
    """
    tail = StateGraph(SolvitaState)
    codegen_sg = create_codegen_subgraph()
    hacker_sg = create_hacker_subgraph()

    tail.add_node("codegen_phase", codegen_sg)
    tail.add_node("phase_transition_2", phase_transition_node)
    tail.add_node("enter_hack_phase", enter_hack_phase_node)
    tail.add_node("hacker_phase", hacker_sg)
    tail.add_node("phase_transition_3", phase_transition_node)
    tail.add_node("terminal_hack_failure", terminal_hack_failure_node)

    tail.set_entry_point("codegen_phase")
    tail.add_edge("codegen_phase", "phase_transition_2")
    tail.add_edge("phase_transition_2", "enter_hack_phase")
    tail.add_edge("enter_hack_phase", "hacker_phase")
    tail.add_conditional_edges(
        "hacker_phase",
        hack_outcome_routing,
        {
            "loop_codegen": "phase_transition_3",
            "terminal_failure": "terminal_hack_failure",
            "final_ac": END,
        },
    )
    tail.add_edge("phase_transition_3", "codegen_phase")
    tail.add_edge("terminal_hack_failure", END)
    return tail.compile()


# ============================================================
# Top-level Orchestrator（含 Hack→CodeGen 回环）
# ============================================================

def create_solvita_workflow():
    """
    Top-level orchestrator: Abstract → TestGen → CodeGen → Hacker, with Hack→CodeGen loop.

    Normal path (no adversarial break):
        abstract_phase → phase_transition_0 → testgen_phase → phase_transition_1
        → solver_skill_plan → codegen_phase → phase_transition_2 → hacker_phase → END (final AC)

    Loop path (hack finds a bug):
        hacker_phase → phase_transition_3 → codegen_phase
        (solver_skill_plan is not re-run; only first entry to codegen uses graph augmentation)
        (failed hack cases are appended into tests.generated_tests)

    When iteration >= max_iterations, ``hack_outcome_routing`` may return ``final_ac``.
    """
    workflow = StateGraph(SolvitaState)

    abstract_sg = create_abstract_subgraph()
    testgen_sg = create_testgen_subgraph()
    codegen_sg = create_codegen_subgraph()
    hacker_sg = create_hacker_subgraph()

    workflow.add_node("abstract_phase", abstract_sg)
    workflow.add_node("failure_bank_lookup", failure_bank_lookup_node)
    workflow.add_node("pre_solve_controller", pre_solve_controller_node)
    workflow.add_node("phase_transition_0", phase_transition_node)  # ABSTRACT→TESTGEN
    workflow.add_node("bootstrap_tests", bootstrap_tests_node)
    workflow.add_node("testgen_phase", testgen_sg)
    workflow.add_node("phase_transition_1", phase_transition_node)  # TESTGEN→CODEGEN
    workflow.add_node("solver_skill_plan", solver_skill_plan_node)
    workflow.add_node("solver_skill_plan_ensemble", solver_skill_plan_ensemble_node)
    workflow.add_node("codegen_phase", codegen_sg)
    workflow.add_node("verifier_phase", verifier_phase_node)
    workflow.add_node("post_verify_controller", post_verify_controller_node)
    workflow.add_node("phase_transition_2", phase_transition_node)  # CODEGEN→HACKER
    workflow.add_node("enter_hack_phase", enter_hack_phase_node)
    workflow.add_node("hacker_phase", hacker_sg)
    workflow.add_node("phase_transition_3", phase_transition_node)  # HACKER→CODEGEN（回环）
    workflow.add_node("terminal_hack_failure", terminal_hack_failure_node)

    workflow.set_entry_point("abstract_phase")
    workflow.add_edge("abstract_phase", "failure_bank_lookup")
    workflow.add_edge("failure_bank_lookup", "pre_solve_controller")
    workflow.add_edge("pre_solve_controller", "phase_transition_0")
    workflow.add_edge("phase_transition_0", "bootstrap_tests")
    workflow.add_conditional_edges(
        "bootstrap_tests",
        bootstrap_routing,
        {
            "run_full_testgen": "testgen_phase",
            "skip_full_testgen": "phase_transition_1",
        },
    )
    workflow.add_edge("testgen_phase", "phase_transition_1")
    workflow.add_conditional_edges(
        "phase_transition_1",
        plan_or_codegen_routing,
        {
            "skill_plan": "solver_skill_plan",
            "direct_codegen": "codegen_phase",
        },
    )
    workflow.add_edge("solver_skill_plan_ensemble", END)
    workflow.add_edge("solver_skill_plan", "codegen_phase")
    workflow.add_conditional_edges(
        "codegen_phase",
        post_codegen_routing,
        {
            "to_verifier": "verifier_phase",
            "end": END,
        },
    )
    workflow.add_edge("verifier_phase", "post_verify_controller")
    workflow.add_conditional_edges(
        "post_verify_controller",
        post_verify_routing,
        {
            "repair": "codegen_phase",
            "escalate_testgen": "testgen_phase",
            "accept_hack": "phase_transition_2",
            "accept_end": END,
        },
    )
    workflow.add_edge("phase_transition_2", "enter_hack_phase")
    workflow.add_edge("enter_hack_phase", "hacker_phase")

    # Hack 结果路由（顶层）：找到 Bug → 回环 CodeGen；无法攻破 → Final AC
    workflow.add_conditional_edges(
        "hacker_phase",
        hack_outcome_routing,
        {
            "loop_codegen": "phase_transition_3",
            "terminal_failure": "terminal_hack_failure",
            "final_ac": END,
        },
    )

    # 回环：HACKER → CODEGEN（保留 messages，重置 hack_round，带 hack 失败用例重新答题）
    workflow.add_edge("phase_transition_3", "codegen_phase")
    workflow.add_edge("terminal_hack_failure", END)

    compiled = workflow.compile()
    logger.info("Solvita Orchestrator workflow compiled (Abstract→TestGen→CodeGen→Hacker + loop)")
    return compiled


# ============================================================
# Entry point
# ============================================================

def run_workflow(raw_problem: Dict[str, Any], config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Execute the Solvita workflow on a problem.

    Args:
        raw_problem: Problem description and public tests.
        config: Runtime configuration (optional).

    Returns:
        Final state after workflow completion.

    When ``solver_network.enabled`` and ``ensemble_skill_plans.enabled`` and a log root
    (``benchmark_output_dir`` or ``branch_log_dir``) is set, creates::

        {root}/logs/ensemble_cases/{stem}/00_pre_ensemble.log

    for Abstract→TestGen, then each ensemble branch writes ``branch_XX.log`` in the same folder.
    """
    if config is None:
        config = {
            "max_iterations": 5,
            "max_hack_rounds": 3,
        }
    ensure_token_usage_accumulator(config)

    logger.info("=" * 60)
    logger.info("Starting Solvita Workflow (Abstract → TestGen → CodeGen → Hacker + loop)")
    logger.info("=" * 60)

    initial_state = create_initial_state(raw_problem, config)
    setup_ensemble_case_logging(initial_state)
    workflow = create_solvita_workflow()

    final_state: Dict[str, Any] | None = None
    try:
        final_state = workflow.invoke(
            initial_state,
            {"recursion_limit": 200},
        )
    finally:
        merged_cfg = (final_state or initial_state).get("config") or {}
        teardown_ensemble_pre_log_sink(merged_cfg)

    logger.info("=" * 60)
    logger.info(f"Workflow Complete: {final_state.get('status', 'unknown')}")
    logger.info(f"Final Phase: {final_state.get('current_phase', 'unknown')}")
    logger.info(f"Iterations: {final_state.get('iteration', 0)}")
    logger.info(f"LLM Calls: {final_state.get('llm_calls', 0)}")
    logger.info(f"Pass Rate: {final_state['tests'].get('pass_rate', 0.0):.1%}")
    token_usage = get_token_usage_snapshot(final_state.get("config", {}))
    final_state["prompt_tokens"] = token_usage["prompt_tokens"]
    final_state["completion_tokens"] = token_usage["completion_tokens"]
    final_state["token_usage_source"] = token_usage["token_usage_source"]
    logger.info(f"Prompt Tokens: {token_usage['prompt_tokens']}")
    logger.info(f"Completion Tokens: {token_usage['completion_tokens']}")
    logger.info(f"Token Usage Source: {token_usage['token_usage_source']}")
    logger.info("=" * 60)

    return final_state


def stream_workflow(
    raw_problem: dict,
    config: dict | None = None,
) -> dict:
    """Execute the Solvita workflow and emit NDJSON events via ``src.events``.

    Delegates to ``run_workflow`` so the CLI and direct execution share the same code path.
    Phase events are emitted from each node, so the CLI receives real-time progress.
    """
    if config is None:
        config = {"max_iterations": 5, "max_hack_rounds": 3}

    events.emit(
        "solve_start",
        problem_id=str(
            (raw_problem or {}).get("problem_id")
            or extract_problem_code(raw_problem or {})
            or "unknown"
        ),
        max_iterations=config.get("max_iterations", 5),
    )

    final_state = run_workflow(raw_problem, config)

    token_usage = get_token_usage_snapshot(final_state.get("config") or config)
    tests_data = final_state.get("tests") or {}
    events.emit(
        "final",
        status=final_state.get("status", "unknown"),
        iterations=final_state.get("iteration", 0),
        llm_calls=final_state.get("llm_calls", 0),
        passed=tests_data.get("passed_tests", 0),
        total=tests_data.get("total_tests", 0),
        pass_rate=tests_data.get("pass_rate", 0.0),
        prompt_tokens=token_usage["prompt_tokens"],
        completion_tokens=token_usage["completion_tokens"],
    )

    return final_state
