"""LangGraph Workflow Definition for Solvita Agent

Workflow overview (三阶段子图架构)
=====================================
Phase 1: TestGen  — generate_tests
          ↓ phase_transition (清空 messages)
Phase 2: CodeGen  — plan_solution → generate_code/tests → run_tests
                    → unified_check → memory settlement → status_routing
          ↓ phase_transition (清空 messages)
Phase 3: Hacker   — hack_test → hack_routing → update_hacker_memory
                    → END | re-inject failures back to CodeGen (via top-level)
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
    update_test_memory_node,
    update_oracle_memory_node,
    hack_test_node,
    join_ready_node,
    join_wait_node,
    status_routing,
    compilation_routing,
    hack_routing,
    join_routing,
    phase_transition_node,
    update_hacker_memory_node,
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
    g.add_node("update_test_memory", update_test_memory_node)
    g.add_node("update_oracle_memory", update_oracle_memory_node)
    g.add_node("analyze_feedback", analyze_feedback_node)

    g.set_entry_point("plan_solution")

    # plan -> parallel: generate_code (tests already generated in Phase 1)
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

    # join_ready acts as a barrier waiting for both test + compile
    # In Phase 2, tests are already ready from Phase 1, so join goes straight to run_tests
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
    g.add_edge("update_solve_memory", "update_test_memory")
    g.add_edge("update_test_memory", "update_oracle_memory")

    # status_routing: "continue" loops internally; "hack" / "end" exit the subgraph
    g.add_conditional_edges(
        "update_oracle_memory",
        status_routing,
        {
            "continue": "analyze_feedback",
            "hack": END,   # signals top-level to proceed to Phase 3
            "end": END,
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
    g.add_node("update_hacker_memory", update_hacker_memory_node)

    g.set_entry_point("hack_test")

    g.add_conditional_edges(
        "hack_test",
        hack_routing,
        {
            "hack_again": "hack_test",
            "hack_failed": "update_hacker_memory",
            "end": "update_hacker_memory",
        },
    )

    g.add_edge("update_hacker_memory", END)

    return g.compile()


# ============================================================
# Top-level Orchestrator
# ============================================================

def create_solvita_workflow():
    """
    顶层 Orchestrator 图：串联三个 Phase 子图，Phase 间插入 phase_transition_node。

    拓扑：
        testgen_phase
          → phase_transition_1 (TESTGEN → CODEGEN, 清空 messages)
          → codegen_phase
          → phase_transition_2 (CODEGEN → HACKER, 清空 messages)
          → hacker_phase
          → END
    """
    workflow = StateGraph(SolvitaState)

    # 编译三个子图
    testgen_sg = create_testgen_subgraph()
    codegen_sg = create_codegen_subgraph()
    hacker_sg = create_hacker_subgraph()

    # 注册节点
    workflow.add_node("testgen_phase", testgen_sg)
    workflow.add_node("phase_transition_1", phase_transition_node)
    workflow.add_node("codegen_phase", codegen_sg)
    workflow.add_node("phase_transition_2", phase_transition_node)
    workflow.add_node("hacker_phase", hacker_sg)

    # 边
    workflow.set_entry_point("testgen_phase")
    workflow.add_edge("testgen_phase", "phase_transition_1")
    workflow.add_edge("phase_transition_1", "codegen_phase")
    workflow.add_edge("codegen_phase", "phase_transition_2")
    workflow.add_edge("phase_transition_2", "hacker_phase")
    workflow.add_edge("hacker_phase", END)

    compiled = workflow.compile()
    logger.info("Solvita Orchestrator workflow compiled successfully (3-phase subgraph architecture)")
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
    logger.info("Starting Solvita Workflow (3-Phase Orchestrator)")
    logger.info("=" * 60)

    initial_state = create_initial_state(raw_problem, config)
    workflow = create_solvita_workflow()

    final_state = workflow.invoke(
        initial_state,
        {"recursion_limit": 150},
    )

    logger.info("=" * 60)
    logger.info(f"Workflow Complete: {final_state.get('status', 'unknown')}")
    logger.info(f"Final Phase: {final_state.get('current_phase', 'unknown')}")
    logger.info(f"Iterations: {final_state.get('iteration', 0)}")
    logger.info(f"LLM Calls: {final_state.get('llm_calls', 0)}")
    logger.info(f"Pass Rate: {final_state['tests'].get('pass_rate', 0.0):.1%}")
    logger.info("=" * 60)

    return final_state
