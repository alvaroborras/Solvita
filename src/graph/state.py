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
    # Canonical problem representation (populated by abstract_problem_node)
    canonical: Dict[str, Any]
    # Whitelist-filtered algorithmic tags from abstract_problem_node
    tags_selected: List[str]
    abstract_confidence: float
    abstract_trace: Dict[str, Any]


class PlanData(TypedDict, total=False):
    """Solution planning data (abstract_problem_node or legacy plan_solution_node)"""
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
    oracle_route: Optional[str]
    accepted_artifact_kind: Optional[str]
    verifier_provenance: Optional[Dict[str, Any]]
    certification_evidence: List[Dict[str, Any]]
    cert_ratio: float
    certified_count: int
    certified_target_count: int
    oracle_primary_family_id: Optional[str]
    oracle_fallback_family_id: Optional[str]
    oracle_selected_family_id: Optional[str]
    candidate_family_pool: List[str]
    oracle_compile_success: bool
    oracle_public_self_check_pass: bool
    oracle_probe_pack_pass: bool
    checker_fallback_used: bool
    solver_attempt_count: int
    selected_template_name: Optional[str]
    prompt_char_stats: Dict[str, int]
    compact_retry_count: int


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
    oracle_event_metadata: Annotated[Dict[str, Any], merge_dict]
    oracle_memory_decision: Annotated[Dict[str, Any], merge_dict]

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
    analyst_report: Dict[str, Any]
    validator_rejection_reasons: List[str]
    # T3.2 v2 Hacker state contract fields (hacker-system.md §4.1)
    hack_result: str            # "BREAK" | "SAFE" | "GEN_FAILED"
    generator_route_used: str   # "anti_hash" | "semantic" | "stress" | "failed"
    hack_failure_type: str      # "WA" | "RE" | "TLE" | "MLE" | "NONE"
    generator_failure_kind: str
    generator_failure_reason: str

    # -- Phase routing (set by phase_transition_node) --
    current_phase: str  # "ABSTRACT" | "TESTGEN" | "CODEGEN" | "HACKER"

    # One-shot skill-graph injection for first initial codegen only
    solver_network_oneshot_spent: bool

    # -- Metadata --
    execution_log: Annotated[List[str], add]
    llm_calls: Annotated[int, add]
    prompt_tokens: int
    completion_tokens: int
    token_usage_source: str


def _merge_runtime_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply defaults for nested runtime knobs (mutates a copy)."""
    cfg = dict(config)
    sn = cfg.get("solver_network")
    if not isinstance(sn, dict):
        sn = {}
    cfg["solver_network"] = {
        "enabled": False,
        "graph_dir": "",
        "top_k_problems": 4,
        "sample_k": 5,
        "temperature": 1.0,
        **sn,
    }
    return cfg


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
    config = _merge_runtime_config(config)
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
            tags_selected=[],
            abstract_confidence=0.0,
            abstract_trace={},
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
            oracle_route=None,
            accepted_artifact_kind=None,
            verifier_provenance=None,
            certification_evidence=[],
            cert_ratio=0.0,
            certified_count=0,
            certified_target_count=0,
            oracle_primary_family_id=None,
            oracle_fallback_family_id=None,
            oracle_selected_family_id=None,
            candidate_family_pool=[],
            oracle_compile_success=False,
            oracle_public_self_check_pass=False,
            oracle_probe_pack_pass=False,
            checker_fallback_used=False,
            solver_attempt_count=0,
            selected_template_name=None,
            prompt_char_stats={},
            compact_retry_count=0,
        ),
        feedback=FeedbackData(
            feedback={},
            suggested_fixes=[],
        ),
        oracle_event_metadata={},
        oracle_memory_decision={},

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
        analyst_report={},
        validator_rejection_reasons=[],
        hack_result="",
        generator_route_used="",
        hack_failure_type="",
        generator_failure_kind="",
        generator_failure_reason="",
        current_phase="ABSTRACT",

        solver_network_oneshot_spent=False,

        # Metadata
        execution_log=[],
        llm_calls=0,
        prompt_tokens=0,
        completion_tokens=0,
        token_usage_source="untracked",
    )
