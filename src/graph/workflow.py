"""LangGraph Workflow Definition for Solvita Agent

This module defines the complete workflow graph that orchestrates the
problem-solving process from problem input to final solution.

Workflow:
1. Parse problem → 2. Retrieve knowledge → 3. Plan solution → 4. Generate tests
→ 5. Generate code → 6. Compile → 7. Run tests → 8. Check success
→ 9. (if failed) Analyze feedback → back to 5
→ 10. (if success or max iterations) Finalize
"""

from langgraph.graph import StateGraph, END
from src.graph.state import SolvitaState, create_initial_state
from src.graph.nodes import (
    parse_problem_node,
    retrieve_knowledge_node,
    plan_solution_node,
    generate_tests_node,
    generate_code_node,
    compile_code_node,
    run_tests_node,
    check_success_node,
    check_should_continue_node,
    analyze_feedback_node,
    finalize_solution_node,
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

    # Phase 1: Problem Understanding
    workflow.add_node("parse_problem", parse_problem_node)

    # Phase 2: Knowledge Retrieval
    workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)

    # Phase 3: Planning
    workflow.add_node("plan_solution", plan_solution_node)

    # Phase 4: Test Generation (only once at the beginning)
    workflow.add_node("generate_tests", generate_tests_node)

    # Phase 5: Code Generation (can be repeated in iterations)
    workflow.add_node("generate_code", generate_code_node)

    # Phase 6: Compilation
    workflow.add_node("compile_code", compile_code_node)

    # Phase 7: Testing
    workflow.add_node("run_tests", run_tests_node)

    # Phase 8: Success Check
    workflow.add_node("check_success", check_success_node)

    # Phase 9: Iteration Control
    workflow.add_node("check_continue", check_should_continue_node)

    # Phase 10: Feedback Analysis (for failed iterations)
    workflow.add_node("analyze_feedback", analyze_feedback_node)

    # Phase 11: Finalization
    workflow.add_node("finalize", finalize_solution_node)

    # ========== Define Edges ==========

    # Set entry point
    workflow.set_entry_point("parse_problem")

    # Linear flow for initial setup
    workflow.add_edge("parse_problem", "retrieve_knowledge")
    workflow.add_edge("retrieve_knowledge", "plan_solution")
    workflow.add_edge("plan_solution", "generate_tests")

    # Start code generation iteration
    workflow.add_edge("generate_tests", "generate_code")

    # After code generation, compile
    workflow.add_edge("generate_code", "compile_code")

    # Conditional: compilation success or failure
    workflow.add_conditional_edges(
        "compile_code",
        compilation_routing,
        {
            "success": "run_tests",  # If compiled, run tests
            "failed": "analyze_feedback",  # If failed, analyze errors
        },
    )

    # After running tests, check if all passed
    workflow.add_edge("run_tests", "check_success")

    # After checking success, decide whether to continue
    workflow.add_edge("check_success", "check_continue")

    # Conditional: continue iteration or finalize
    workflow.add_conditional_edges(
        "check_continue",
        status_routing,
        {
            "continue": "analyze_feedback",  # Continue → analyze feedback → regenerate
            "end": "finalize",  # Success or max iterations → finalize
        },
    )

    # After analyzing feedback, regenerate code
    workflow.add_edge("analyze_feedback", "generate_code")

    # Finalize is the terminal node
    workflow.add_edge("finalize", END)

    # Compile the graph
    compiled_workflow = workflow.compile()

    logger.info("✓ Solvita workflow graph compiled successfully")

    return compiled_workflow


def visualize_workflow(output_path: str = "workflow_diagram.png"):
    """
    Generate a visual diagram of the workflow.

    Args:
        output_path: Path to save the diagram
    """
    try:
        workflow = create_solvita_workflow()
        # Get the graph representation
        graph = workflow.get_graph()
        # Draw the graph
        graph_image = graph.draw_mermaid_png()

        with open(output_path, "wb") as f:
            f.write(graph_image)

        logger.info(f"✓ Workflow diagram saved to {output_path}")
    except Exception as e:
        logger.warning(f"Could not generate diagram: {e}")
        logger.info("Install pygraphviz for diagram generation: pip install pygraphviz")


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

    # Execute the workflow
    final_state = workflow.invoke(initial_state)

    logger.info("=" * 60)
    logger.info(f"Workflow Complete: {final_state.get('status', 'unknown')}")
    logger.info(f"Iterations: {final_state.get('iteration', 0)}")
    logger.info(f"LLM Calls: {final_state.get('llm_calls', 0)}")
    logger.info(f"Pass Rate: {final_state['tests'].get('pass_rate', 0.0):.1%}")
    logger.info("=" * 60)

    return final_state


# ========== Workflow Execution Modes ==========

def run_workflow_streaming(raw_problem: Dict[str, Any], config: Dict[str, Any] = None):
    """
    Execute workflow with streaming output for each node.

    Yields state after each node execution for real-time monitoring.
    """
    if config is None:
        config = {"max_iterations": 5}

    initial_state = create_initial_state(raw_problem, config)
    workflow = create_solvita_workflow()

    logger.info("Starting streaming workflow execution...")

    # Stream events from the workflow
    for event in workflow.stream(initial_state):
        node_name = list(event.keys())[0]
        node_output = event[node_name]

        logger.info(f"→ Completed node: {node_name}")

        # Yield for external monitoring/UI updates
        yield {
            "node": node_name,
            "output": node_output,
            "timestamp": None,  # Add timestamp if needed
        }


def run_workflow_async(raw_problem: Dict[str, Any], config: Dict[str, Any] = None):
    """
    Execute workflow asynchronously.

    Useful for parallel processing of multiple problems.
    """
    # TODO: Implement async version using ainvoke
    # This would allow processing multiple problems concurrently
    pass


# ========== Mermaid Diagram Definition ==========

WORKFLOW_MERMAID = """
graph TD
    START([Start]) --> parse_problem[Parse Problem]
    parse_problem --> retrieve_knowledge[Retrieve Knowledge]
    retrieve_knowledge --> plan_solution[Plan Solution]
    plan_solution --> generate_tests[Generate Tests]

    generate_tests --> generate_code[Generate Code]
    generate_code --> compile_code[Compile Code]

    compile_code -->|Success| run_tests[Run Tests]
    compile_code -->|Failed| analyze_feedback[Analyze Feedback]

    run_tests --> check_success[Check Success]
    check_success --> check_continue[Check Continue?]

    check_continue -->|Continue| analyze_feedback
    check_continue -->|End| finalize[Finalize Solution]

    analyze_feedback --> generate_code

    finalize --> END([End])

    style START fill:#90EE90
    style END fill:#FFB6C1
    style parse_problem fill:#E6E6FA
    style retrieve_knowledge fill:#E6E6FA
    style plan_solution fill:#FFE4B5
    style generate_tests fill:#FFE4B5
    style generate_code fill:#87CEEB
    style compile_code fill:#DDA0DD
    style run_tests fill:#DDA0DD
    style check_success fill:#F0E68C
    style check_continue fill:#F0E68C
    style analyze_feedback fill:#FFA07A
    style finalize fill:#98FB98
"""


if __name__ == "__main__":
    # Test workflow creation
    print("Creating Solvita workflow...")
    workflow = create_solvita_workflow()
    print("✓ Workflow created successfully!")

    # Try to visualize
    print("\nAttempting to generate workflow diagram...")
    visualize_workflow()

    # Print Mermaid diagram for manual visualization
    print("\nMermaid Diagram (paste into https://mermaid.live):")
    print(WORKFLOW_MERMAID)
