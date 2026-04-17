"""LangGraph Workflow Definition for Solvita Agent

Workflow overview (Abstract → TestGen → CodeGen → Hacker + Hack→CodeGen loop)
============================================================================
Phase 0: Abstract — abstract_problem (canonical + whitelist tags + confidence)
          ↓ phase_transition_0 (clear messages)
Phase 1: TestGen  — generate_tests
          ↓ phase_transition_1 (clear messages)
Phase 1b: Solver plan (optional) — solver_skill_plan (when solver_network.enabled)
          builds DAG + skill selection + solver_graph_augmentation_block; skipped on Hack→CodeGen loop
Phase 2: CodeGen  — generate_code/compile → run_tests
                    → memory settlement → status_routing
          ↓ phase_transition_2 (clear messages)
Phase 3: Hacker   — hack_test (≤3 retry) → settle_hacker_memory
          ↓ hack_outcome_routing:
              "loop_codegen" → phase_transition_3 → back to CodeGen
              "final_ac"     → END

Iteration budget: iteration increments per codegen repair round; max_iterations stops the run.
"""

from langgraph.graph import StateGraph, END
from src.graph.state import SolvitaState, create_initial_state
from src.nodes import (
    abstract_problem_node,
    generate_tests_node,
    solver_skill_plan_node,
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
    workflow.add_node("phase_transition_0", phase_transition_node)  # ABSTRACT→TESTGEN
    workflow.add_node("testgen_phase", testgen_sg)
    workflow.add_node("phase_transition_1", phase_transition_node)  # TESTGEN→CODEGEN
    workflow.add_node("solver_skill_plan", solver_skill_plan_node)
    workflow.add_node("codegen_phase", codegen_sg)
    workflow.add_node("phase_transition_2", phase_transition_node)  # CODEGEN→HACKER
    workflow.add_node("enter_hack_phase", enter_hack_phase_node)
    workflow.add_node("hacker_phase", hacker_sg)
    workflow.add_node("phase_transition_3", phase_transition_node)  # HACKER→CODEGEN（回环）
    workflow.add_node("terminal_hack_failure", terminal_hack_failure_node)

    workflow.set_entry_point("abstract_phase")
    workflow.add_edge("abstract_phase", "phase_transition_0")
    workflow.add_edge("phase_transition_0", "testgen_phase")
    workflow.add_edge("testgen_phase", "phase_transition_1")
    workflow.add_edge("phase_transition_1", "solver_skill_plan")
    workflow.add_edge("solver_skill_plan", "codegen_phase")
    workflow.add_edge("codegen_phase", "phase_transition_2")
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

    # 回环：HACKER → CODEGEN（清空 messages，重置 hack_round，带 hack 失败用例重新答题）
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
    workflow = create_solvita_workflow()

    final_state = workflow.invoke(
        initial_state,
        {"recursion_limit": 200},
    )

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
