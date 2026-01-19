"""LangGraph Workflow Definition for Solvita Agent

This module defines the complete workflow graph that orchestrates the
problem-solving process from problem input to final solution.

Workflow:
1. Retrieve knowledge → 2. Plan solution → 3. Generate code → 4. Compile ─┐
5. Generate tests ────────────────────────────────────────────────────────┴→ 6. Run tests
→ 7. Check success
→ 8. (if failed) Analyze feedback → back to 3
→ 9. (if success or max iterations) END

Note: retrieve_knowledge and generate_tests run in parallel, but plan_solution 
depends on retrieve_knowledge completing first.
"""

from langgraph.graph import StateGraph, END
from src.graph.state import SolvitaState, create_initial_state
from src.nodes import (
    retrieve_knowledge_node,
    plan_solution_node,
    generate_tests_node,
    generate_code_node,
    compile_code_node,
    run_tests_node,
    unified_check_node,
    analyze_feedback_node,
    status_routing,
    compilation_routing,
)
from typing import Dict, Any
from loguru import logger


def create_solvita_workflow() -> StateGraph:
    """
    Create the complete Solvita LangGraph workflow.

    Returns:
        Compiled StateGraph ready for execution
    """
    # Initialize graph with SolvitaState type
    workflow = StateGraph(SolvitaState)

    # ========== Add Nodes ==========

    # Phase 1: Knowledge Retrieval
    workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)

    # Phase 2: Planning (depends on knowledge)
    workflow.add_node("plan_solution", plan_solution_node)

    # Phase 3: Test Generation (parallel with planning/coding)
    workflow.add_node("generate_tests", generate_tests_node)

    # Phase 4: Code Generation (can be repeated in iterations)
    workflow.add_node("generate_code", generate_code_node)

    # Phase 5: Compilation
    workflow.add_node("compile_code", compile_code_node)

    # Phase 6: Testing
    workflow.add_node("run_tests", run_tests_node)

    # Phase 7: Unified Check and Control
    workflow.add_node("unified_check", unified_check_node)

    # Phase 8: Feedback Analysis (for failed iterations)
    workflow.add_node("analyze_feedback", analyze_feedback_node)

    # ========== Define Edges ==========
    # Simplified sequential workflow (no parallel branches to avoid state conflicts)

    # Set entry point - start with knowledge retrieval
    workflow.set_entry_point("retrieve_knowledge")

    # Sequential flow: knowledge → tests → plan → code → compile
    workflow.add_edge("retrieve_knowledge", "generate_tests")
    workflow.add_edge("generate_tests", "plan_solution")
    workflow.add_edge("plan_solution", "generate_code")
    workflow.add_edge("generate_code", "compile_code")

    # Conditional: compilation success or failure
    workflow.add_conditional_edges(
        "compile_code",
        compilation_routing,
        {
            "success": "run_tests",  # If compiled, go to run_tests
            "failed": "analyze_feedback",  # If failed, analyze errors directly
        },
    )

    # After running tests, unified check and control
    workflow.add_edge("run_tests", "unified_check")

    # Conditional: check status and decide whether to continue or end
    workflow.add_conditional_edges(
        "unified_check",
        status_routing,
        {
            "continue": "analyze_feedback",  # Continue → analyze feedback → regenerate
            "end": END,  # Success or max iterations → end workflow
        },
    )

    # After analyzing feedback, regenerate code
    workflow.add_edge("analyze_feedback", "generate_code")

    # Compile the graph
    compiled_workflow = workflow.compile()

    logger.info("Solvita workflow graph compiled successfully")

    return compiled_workflow


def run_workflow(raw_problem: Dict[str, Any], config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Execute the Solvita workflow on a problem.

    Args:
        raw_problem: Problem description and public tests
        config: Runtime configuration (optional)

    Returns:
        Final state after workflow completion
    """
    if config is None:
        config = {
            "max_iterations": 5,
            "model": "gpt-4",
            "temperature": 0.1,
        }

    logger.info("=" * 60)
    logger.info("Starting Solvita Workflow")
    logger.info("=" * 60)

    # Create initial state
    initial_state = create_initial_state(raw_problem, config)

    # Create and run workflow
    workflow = create_solvita_workflow()

    # Execute the workflow with increased recursion limit
    # Each iteration involves ~5 nodes, so 5 iterations = 25 nodes + initial = ~30
    final_state = workflow.invoke(
        initial_state,
        {"recursion_limit": 100}
    )

    logger.info("=" * 60)
    logger.info(f"Workflow Complete: {final_state.get('status', 'unknown')}")
    logger.info(f"Iterations: {final_state.get('iteration', 0)}")
    logger.info(f"LLM Calls: {final_state.get('llm_calls', 0)}")
    logger.info(f"Pass Rate: {final_state['tests'].get('pass_rate', 0.0):.1%}")
    logger.info("=" * 60)

    return final_state
