"""LangGraph State Definition

Canonical state schema for the Solvita competitive-programming agent.
Every field accessed via ``state[key]`` or ``state.get(key)`` in any node
MUST be declared here.
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
from operator import add
from langgraph.graph.message import add_messages


# ========== Custom Reducers ==========

def merge_dict(left: Dict, right: Dict) -> Dict:
    """Merge two dicts; right values override left."""
    if left is None:
        return right or {}
    if right is None:
        return left or {}
    result = dict(left)
    result.update(right)
    return result


# ========== Nested Data Structures ==========

class ProblemData(TypedDict, total=False):
    """Problem-related data from parse_problem_node"""
    description: str
    types: List[str]
    constraints: Dict[str, Any]
    public_tests: List[Dict]
    retrieved_knowledge: List[Dict]
    # Canonical problem representation (populated by plan_solution_node)
    canonical: Dict[str, Any]


class PlanData(TypedDict, total=False):
    """Solution planning data from plan_solution_node"""
    solution_plan: Dict[str, Any]
    algorithm_choice: str
    implementation_steps: List[str]
    # Trainable memory fields (populated by plan_solution_node)
    memory_item_ids: List[str]
    memory_advice: str


class SolutionData(TypedDict, total=False):
    """Generated solution data from generate_code_node through run_tests_node"""
    code: str
    version: int
    compilation_success: bool
    compilation_errors: List[str]
    executable_path: Optional[str]
    # Trainable memory fields (populated by generate_code_node)
    memory_item_ids: List[str]
    # Diagnostic mode flag (set by analyze_feedback_node when sanitizers are needed)
    diagnostic_mode: bool


class TestData(TypedDict, total=False):
    """Test-related data from generate_tests_node and run_tests_node"""
    generated_tests: List[Dict]
    total_tests: int
    test_results: List[Dict]
    passed_tests: int
    pass_rate: float
    pending_execution: bool
    ready: bool
    # Checker executable path (set by generate_tests_node)
    checker_exe: Optional[str]
    # Validator executable path (set by generate_tests_node)
    validator_exe: Optional[str]


class FeedbackData(TypedDict, total=False):
    """Feedback data from analyze_feedback_node"""
    feedback: Dict[str, Any]
    suggested_fixes: List[str]


# ========== Main State ==========

class SolvitaState(TypedDict):
    """Core state for Solvita workflow."""

    # -- Input layer (immutable after initialization) --
    raw_problem: Dict[str, Any]
    config: Dict[str, Any]

    # -- Business objects (populated progressively by nodes) --
    problem: Annotated[ProblemData, merge_dict]
    plan: Annotated[PlanData, merge_dict]
    solution: Annotated[SolutionData, merge_dict]
    oracle_solution: Optional[Dict[str, Any]]
    buggy_solution: Optional[Dict[str, Any]]
    tests: Annotated[TestData, merge_dict]
    feedback: Annotated[FeedbackData, merge_dict]

    # -- LLM conversation history --
    messages: Annotated[List[Dict[str, str]], add_messages]

    # -- Control flow --
    iteration: int
    max_iterations: int
    status: str  # "pending" | "success" | "max_iterations" | "error"

    # -- Hack test fields (used by hack_test_node / hack_routing) --
    hack_round: int
    max_hack_rounds: int
    hack_passed: bool
    hack_failures: List[Dict]
    hacker_reward: float
    hacker_memory_item_ids: List[str]
    oracle_memory_item_ids: List[str]

    # -- Phase routing (set by phase_transition_node) --
    current_phase: str  # "TESTGEN" | "CODEGEN" | "HACKER"

    # -- Metadata --
    execution_log: Annotated[List[str], add]
    llm_calls: Annotated[int, add]


def create_initial_state(raw_problem: Dict[str, Any], config: Dict[str, Any]) -> SolvitaState:
    """
    Create initial state with all fields properly initialized.

    Expected raw_problem format::

        {
            "description": str,
            "time_limit": int,   # milliseconds
            "space_limit": int,  # MB
            "public_tests": [{"input": str, "output": str}, ...]
        }
    """
    return SolvitaState(
        # Input
        raw_problem=raw_problem,
        config=config,

        # Business objects
        problem=ProblemData(
            description=raw_problem.get("description", ""),
            types=[],
            constraints={
                "time_limit": raw_problem.get("time_limit"),
                "space_limit": raw_problem.get("space_limit"),
            },
            public_tests=raw_problem.get("public_tests", []),
            retrieved_knowledge=[],
            canonical={},
        ),
        plan=PlanData(
            solution_plan={},
            algorithm_choice="",
            implementation_steps=[],
            memory_item_ids=[],
            memory_advice="",
        ),
        solution=SolutionData(
            code="",
            version=0,
            compilation_success=False,
            compilation_errors=[],
            executable_path=None,
            memory_item_ids=[],
            diagnostic_mode=False,
        ),
        oracle_solution=None,
        buggy_solution=None,
        tests=TestData(
            generated_tests=[],
            total_tests=0,
            test_results=[],
            passed_tests=0,
            pass_rate=0.0,
            pending_execution=False,
            ready=False,
            checker_exe=None,
            validator_exe=None,
        ),
        feedback=FeedbackData(
            feedback={},
            suggested_fixes=[],
        ),

        # LLM conversation history
        messages=[],

        # Control flow
        iteration=0,
        max_iterations=config.get("max_iterations", 5),
        status="pending",

        # Hack test
        hack_round=0,
        max_hack_rounds=config.get("max_hack_rounds", 3),
        hack_passed=False,
        hack_failures=[],
        hacker_reward=0.0,
        hacker_memory_item_ids=[],
        oracle_memory_item_ids=[],
        current_phase="TESTGEN",

        # Metadata
        execution_log=[],
        llm_calls=0,
    )
