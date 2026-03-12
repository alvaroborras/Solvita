"""LangGraph Workflow Definition for Solvita Agent

Workflow overview (三阶段子图架构 + Hack→CodeGen 回环)
========================================================
Phase 1: TestGen  — generate_tests
          ↓ phase_transition_1 (清空 messages)
Phase 2: CodeGen  — plan_solution → generate_code/compile → run_tests
                    → memory settlement → status_routing
          ↓ phase_transition_2 (清空 messages)
Phase 3: Hacker   — hack_test (≤3 retry) → update_hacker_memory
          ↓ hack_outcome_routing:
              "loop_codegen" → phase_transition_3 → 回 Phase 2
              "final_ac"     → END (解法绝对强健)

回环保护:  iteration 每轮 CodeGen 自增，超过 max_iterations 终止整个流程。
"""

from langgraph.graph import StateGraph, END
from src.graph.state import SolvitaState, create_initial_state
from src.nodes import (
    plan_solution_node,
    generate_tests_node,
    generate_code_node,
    compile_code_node,
    run_tests_node,
    unified_check_node,
    analyze_feedback_node,
    update_plan_memory_node,
    update_solve_memory_node,
    update_oracle_memory_node,
    hack_test_node,
    join_ready_node,
    join_wait_node,
    status_routing,
    compilation_routing,
    hack_routing,
    hack_outcome_routing,
    phase_transition_node,
    settle_hacker_memory,
)
from typing import Dict, Any
from loguru import logger


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

    g.add_node("plan_solution", plan_solution_node)
    g.add_node("generate_code", generate_code_node)
    g.add_node("compile_code", compile_code_node)
    g.add_node("join_ready", join_ready_node)
    g.add_node("join_wait", join_wait_node)
    g.add_node("run_tests", run_tests_node)
    g.add_node("unified_check", unified_check_node)
    g.add_node("update_plan_memory", update_plan_memory_node)
    g.add_node("update_solve_memory", update_solve_memory_node)
    g.add_node("update_oracle_memory", update_oracle_memory_node)
    g.add_node("analyze_feedback", analyze_feedback_node)

    g.set_entry_point("plan_solution")

    g.add_edge("plan_solution", "generate_code")
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

    g.add_edge("run_tests", "unified_check")
    g.add_edge("unified_check", "update_plan_memory")
    g.add_edge("update_plan_memory", "update_solve_memory")
    g.add_edge("update_solve_memory", "update_oracle_memory")

    g.add_conditional_edges(
        "update_oracle_memory",
        status_routing,
        {
            "continue": "analyze_feedback",
            "hack": END,   # 解法通过所有测试，出 Phase 2 → 进 Phase 3
            "end": END,    # 超出迭代次数，放弃
        },
    )

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
    顶层 Orchestrator 图：三 Phase 子图 + Hack→CodeGen 回环。

    正常路径（Hacker 无法找到 Bug）：
        testgen_phase → phase_transition_1
        → codegen_phase → phase_transition_2
        → hacker_phase → END (Final AC)

    回环路径（Hacker 发现 Bug）：
        hacker_phase → phase_transition_3 → codegen_phase
        （Hack 失败的测试用例已被 hack_test_node 追加进 tests.generated_tests）

    熔断保护：iteration >= max_iterations 时，hack_outcome_routing 也返回 final_ac。
    """
    workflow = StateGraph(SolvitaState)

    # 编译三个子图
    testgen_sg = create_testgen_subgraph()
    codegen_sg = create_codegen_subgraph()
    hacker_sg = create_hacker_subgraph()

    # 注册节点
    workflow.add_node("testgen_phase", testgen_sg)
    workflow.add_node("phase_transition_1", phase_transition_node)  # TESTGEN→CODEGEN
    workflow.add_node("codegen_phase", codegen_sg)
    workflow.add_node("phase_transition_2", phase_transition_node)  # CODEGEN→HACKER
    workflow.add_node("hacker_phase", hacker_sg)
    workflow.add_node("phase_transition_3", phase_transition_node)  # HACKER→CODEGEN（回环）

    # 正向路径
    workflow.set_entry_point("testgen_phase")
    workflow.add_edge("testgen_phase", "phase_transition_1")
    workflow.add_edge("phase_transition_1", "codegen_phase")
    workflow.add_edge("codegen_phase", "phase_transition_2")
    workflow.add_edge("phase_transition_2", "hacker_phase")

    # Hack 结果路由（顶层）：找到 Bug → 回环 CodeGen；无法攻破 → Final AC
    workflow.add_conditional_edges(
        "hacker_phase",
        hack_outcome_routing,
        {
            "loop_codegen": "phase_transition_3",
            "final_ac": END,
        },
    )

    # 回环：HACKER → CODEGEN（清空 messages，重置 hack_round，带 hack 失败用例重新答题）
    workflow.add_edge("phase_transition_3", "codegen_phase")

    compiled = workflow.compile()
    logger.info("Solvita Orchestrator workflow compiled (3-phase + Hack→CodeGen loop)")
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

    logger.info("=" * 60)
    logger.info("Starting Solvita Workflow (3-Phase + Hack→CodeGen Loop)")
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
    logger.info("=" * 60)

    return final_state
