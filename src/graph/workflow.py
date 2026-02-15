"""LangGraph Workflow Definition for Solvita Agent

Workflow overview
=================
1. plan_solution  (canonical problem + strategy selection)
   fan-out ->  2a. generate_tests  (parallel)
   fan-out ->  2b. generate_code   (parallel)
3. generate_code -> compile_code
   join   ->  run_tests  (waits for both tests + compiled code)
4. unified_check -> update_plan_memory -> update_solve_memory
5. status_routing:
   - "continue" -> analyze_feedback -> generate_code  (iterate)
   - "hack"     -> hack_test -> hack_routing
                      hack_again -> hack_test
                      hack_failed -> analyze_feedback
                      end -> END
   - "end"      -> END
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
    hack_test_node,
    join_ready_node,
    join_wait_node,
    status_routing,
    compilation_routing,
    hack_routing,
    join_routing,
)
from typing import Dict, Any
from loguru import logger


def create_solvita_workflow() -> StateGraph:
    """
    Create the complete Solvita LangGraph workflow.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(SolvitaState)

    # ========== Nodes ==========

    # Phase 1: Planning
    workflow.add_node("plan_solution", plan_solution_node)

    # Phase 2: Parallel generation
    workflow.add_node("generate_tests", generate_tests_node)
    workflow.add_node("generate_code", generate_code_node)

    # Phase 3: Compilation + test execution
    workflow.add_node("compile_code", compile_code_node)
    workflow.add_node("join_ready", join_ready_node)
    workflow.add_node("join_wait", join_wait_node)
    workflow.add_node("run_tests", run_tests_node)

    # Phase 4: Evaluation + memory settlement
    workflow.add_node("unified_check", unified_check_node)
    workflow.add_node("update_plan_memory", update_plan_memory_node)
    workflow.add_node("update_solve_memory", update_solve_memory_node)

    # Phase 5: Adversarial hack testing
    workflow.add_node("hack_test", hack_test_node)

    # Phase 6: Feedback analysis (for failed iterations)
    workflow.add_node("analyze_feedback", analyze_feedback_node)

    # ========== Edges ==========

    # Entry point
    workflow.set_entry_point("plan_solution")

    # Parallel fan-out: plan -> tests AND plan -> code
    workflow.add_edge("plan_solution", "generate_tests")
    workflow.add_edge("plan_solution", "generate_code")

    # Code generation -> compilation
    workflow.add_edge("generate_code", "compile_code")

    # Conditional: compilation success or failure
    workflow.add_conditional_edges(
        "compile_code",
        compilation_routing,
        {
            "success": "join_ready",
            "failed": "analyze_feedback",
        },
    )

    # Join: generate_tests -> join_ready (waits for compile_code too)
    workflow.add_edge("generate_tests", "join_ready")

    # Conditional join barrier before running tests
    workflow.add_conditional_edges(
        "join_ready",
        join_routing,
        {
            "ready": "run_tests",
            "wait": "join_wait",
        },
    )

    # After running tests, check + settle memory
    workflow.add_edge("run_tests", "unified_check")
    workflow.add_edge("unified_check", "update_plan_memory")
    workflow.add_edge("update_plan_memory", "update_solve_memory")

    # Status routing (after both memory updates are settled)
    workflow.add_conditional_edges(
        "update_solve_memory",
        status_routing,
        {
            "continue": "analyze_feedback",
            "hack": "hack_test",
            "end": END,
        },
    )

    # Hack test adversarial phase
    workflow.add_conditional_edges(
        "hack_test",
        hack_routing,
        {
            "hack_again": "hack_test",
            "hack_failed": "analyze_feedback",
            "end": END,
        },
    )

    # Feedback -> regenerate code
    workflow.add_edge("analyze_feedback", "generate_code")

    compiled_workflow = workflow.compile()
    logger.info("Solvita workflow graph compiled successfully")
    return compiled_workflow


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
    logger.info("Starting Solvita Workflow")
    logger.info("=" * 60)

    initial_state = create_initial_state(raw_problem, config)
    workflow = create_solvita_workflow()

    # Each iteration involves ~7 nodes; 5 iterations + hack rounds = ~50
    final_state = workflow.invoke(
        initial_state,
        {"recursion_limit": 100},
    )

    logger.info("=" * 60)
    logger.info(f"Workflow Complete: {final_state.get('status', 'unknown')}")
    logger.info(f"Iterations: {final_state.get('iteration', 0)}")
    logger.info(f"LLM Calls: {final_state.get('llm_calls', 0)}")
    logger.info(f"Pass Rate: {final_state['tests'].get('pass_rate', 0.0):.1%}")
    logger.info("=" * 60)

    return final_state
