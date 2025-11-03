"""LangGraph State Definition - Simplified

Minimal state focusing on core workflow interfaces.
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
from operator import add


# ========== Nested Data Structures ==========

class ProblemData(TypedDict, total=False):
    """Problem-related data from parse_problem_node"""
    description: str
    types: List[str]
    constraints: Dict[str, Any]
    public_tests: List[Dict]
    retrieved_knowledge: List[Dict]


class PlanData(TypedDict, total=False):
    """Solution planning data from plan_solution_node"""
    solution_plan: Dict[str, Any]
    algorithm_choice: str
    implementation_steps: List[str]


class SolutionData(TypedDict, total=False):
    """Generated solution data from generate_code_node through run_tests_node"""
    code: str
    version: int
    compilation_success: bool
    compilation_errors: List[str]
    executable_path: Optional[str]


class TestData(TypedDict, total=False):
    """Test-related data from generate_tests_node and run_tests_node"""
    generated_tests: List[Dict]
    total_tests: int
    test_results: List[Dict]
    passed_tests: int
    pass_rate: float


class FeedbackData(TypedDict, total=False):
    """Feedback data from analyze_feedback_node"""
    feedback: Dict[str, Any]
    suggested_fixes: List[str]


# ========== Main State ==========

class SolvitaState(TypedDict):
    """Core state for Solvita workflow - minimal and focused"""

    # Input layer (never modified)
    raw_problem: Dict[str, Any]
    config: Dict[str, Any]

    # Business objects layer (populated progressively by nodes)
    problem: ProblemData
    plan: PlanData
    solution: SolutionData
    tests: TestData
    feedback: FeedbackData

    # Control flow layer
    iteration: int
    max_iterations: int
    status: str  # "pending" | "success" | "max_iterations" | "error"

    # Metadata layer
    execution_log: Annotated[List[str], add]
    llm_calls: int


def create_initial_state(raw_problem: Dict[str, Any], config: Dict[str, Any]) -> SolvitaState:
    """Create initial state with all fields properly initialized"""
    return SolvitaState(
        # Input
        raw_problem=raw_problem,
        config=config,

        # Business objects - start empty, populated by nodes
        problem=ProblemData(
            description="",
            types=[],
            constraints={},
            public_tests=[],
            retrieved_knowledge=[],
        ),
        plan=PlanData(
            solution_plan={},
            algorithm_choice="",
            implementation_steps=[],
        ),
        solution=SolutionData(
            code="",
            version=0,
            compilation_success=False,
            compilation_errors=[],
            executable_path=None,
        ),
        tests=TestData(
            generated_tests=[],
            total_tests=0,
            test_results=[],
            passed_tests=0,
            pass_rate=0.0,
        ),
        feedback=FeedbackData(
            feedback={},
            suggested_fixes=[],
        ),

        # Control flow
        iteration=0,
        max_iterations=config.get("max_iterations", 5),
        status="pending",

        # Metadata
        execution_log=[],
        llm_calls=0,
    )
