"""LangGraph State Definition - Simplified

Minimal state focusing on core workflow interfaces.
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
from operator import add


class SolvitaState(TypedDict):
    """Core state for Solvita workflow - minimal and focused"""

    # Input
    raw_problem: Dict[str, Any]
    config: Dict[str, Any]

    # Problem (from parse_problem_node)
    problem_description: str
    constraints: Dict[str, Any]
    problem_types: List[str]
    public_tests: List[Dict]

    # Knowledge (from retrieve_knowledge_node)
    retrieved_knowledge: List[Dict]

    # Planning (from plan_solution_node)
    solution_plan: Dict[str, Any]
    algorithm_choice: str
    implementation_steps: List[str]

    # Testing (from generate_tests_node)
    generated_tests: List[Dict]
    total_tests: int

    # Code (from generate_code_node)
    generated_code: str
    code_version: int

    # Compilation (from compile_code_node)
    compilation_success: bool
    compilation_errors: List[str]
    executable_path: Optional[str]

    # Execution (from run_tests_node)
    test_results: List[Dict]
    passed_tests: int
    pass_rate: float

    # Feedback (from analyze_feedback_node)
    feedback: Dict[str, Any]
    suggested_fixes: List[str]

    # Control flow
    iteration_count: int
    max_iterations: int
    should_continue: bool
    termination_reason: str

    # Output
    final_solution: Optional[str]
    solution_metadata: Dict[str, Any]
    execution_log: Annotated[List[str], add]
    llm_calls: int


def create_initial_state(raw_problem: Dict[str, Any], config: Dict[str, Any]) -> SolvitaState:
    """Create initial state with minimal defaults"""
    return SolvitaState(
        raw_problem=raw_problem,
        config=config,
        problem_description="",
        constraints={},
        problem_types=[],
        public_tests=[],
        retrieved_knowledge=[],
        solution_plan={},
        algorithm_choice="",
        implementation_steps=[],
        generated_tests=[],
        total_tests=0,
        generated_code="",
        code_version=0,
        compilation_success=False,
        compilation_errors=[],
        executable_path=None,
        test_results=[],
        passed_tests=0,
        pass_rate=0.0,
        feedback={},
        suggested_fixes=[],
        iteration_count=0,
        max_iterations=config.get("max_iterations", 5),
        should_continue=True,
        termination_reason="",
        final_solution=None,
        solution_metadata={},
        execution_log=[],
        llm_calls=0,
    )
