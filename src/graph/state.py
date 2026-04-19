"""LangGraph State Definition

Canonical state schema for the Solvita competitive-programming agent.
Every field accessed via ``state[key]`` or ``state.get(key)`` in any node
MUST be declared here.
"""

from pathlib import Path
from typing import TypedDict, List, Dict, Any, Optional, Annotated

import yaml
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
    """Problem payload: raw description, constraints, tests, abstract canonical + tags."""
    description: str
    types: List[str]  # reserved (not read by current pipeline)
    constraints: Dict[str, Any]
    public_tests: List[Dict]
    retrieved_knowledge: List[Dict]  # reserved (not wired in current nodes)
    # Canonical problem representation (populated by abstract_problem_node)
    canonical: Dict[str, Any]
    # Level-1 (primary) tags from abstract_problem_node — used for skill-graph Jaccard / PlannerInput
    tags_selected: List[str]
    # Level-2 (fine-grained) tags — prompt hints only; not fed to similarity_tags / Jaccard
    tags_level2_selected: List[str]
    abstract_confidence: float
    abstract_trace: Dict[str, Any]


class PlanData(TypedDict, total=False):
    """Solution planning: abstract (tags/canonical) + optional solver_skill_plan (DAG/skills)."""
    # Filled by abstract_problem_node; not consumed by codegen today (kept for tracing / future use)
    solution_plan: Dict[str, Any]
    algorithm_choice: str
    implementation_steps: List[str]
    # Trainable memory fields (populated by abstract_problem_node)
    memory_item_ids: List[str]
    memory_advice: str
    # Preformatted skill-graph markdown for first codegen (solver_skill_plan_node when enabled)
    solver_graph_augmentation_block: str
    skill_selection_skill_ids: List[str]
    skill_selection_subproblem_dag: Dict[str, Any]
    # Redundant with text inside solver_graph_augmentation_block; useful for logging / UI
    skill_selection_skills_content_md: str


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
    oracle_solution: Optional[Dict[str, Any]]  # reserved (training / external runners)
    buggy_solution: Optional[Dict[str, Any]]  # reserved (training / external runners)
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
    # T3.2 v2 Hacker state contract (hacker routing / generator metadata)
    hack_result: str            # "BREAK" | "SAFE" | "GEN_FAILED"
    generator_route_used: str   # "anti_hash" | "semantic" | "stress" | "failed"
    hack_failure_type: str      # "WA" | "RE" | "TLE" | "MLE" | "NONE"
    generator_failure_kind: str
    generator_failure_reason: str

    # -- Phase routing (set by phase_transition_node) --
    # solver_skill_plan runs after TESTGEN transition while current_phase is already CODEGEN
    current_phase: str  # "ABSTRACT" | "TESTGEN" | "CODEGEN" | "HACKER"

    # One-shot skill-graph injection for first initial codegen only
    solver_network_oneshot_spent: bool

    best_solution: Annotated[Dict[str, Any], merge_dict]
    best_tests: Annotated[Dict[str, Any], merge_dict]
    best_phase: str  # "test" | "hack"
    has_entered_hack_phase: bool

    # -- Metadata --
    execution_log: Annotated[List[str], add]
    llm_calls: Annotated[int, add]
    prompt_tokens: int
    completion_tokens: int
    token_usage_source: str


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_repo_path(repo_root: Path, raw_path: str) -> str:
    """Resolve a repo-relative or absolute path to an absolute path string."""
    if not raw_path or not isinstance(raw_path, str):
        return ""
    p = raw_path.strip()
    if not p:
        return ""
    path = Path(p)
    if path.is_absolute():
        return str(path.resolve())
    return str((repo_root / path).resolve())


def _fallback_solver_network_defaults(repo_root: Path) -> Dict[str, Any]:
    """Used when ``config/solver_network.yaml`` is missing."""
    return {
        "enabled": False,
        "graph_dir": _resolve_repo_path(
            repo_root, "artifacts/solver_network/latest/graph"
        ),
        "top_k_problems": 4,
        "sample_k": 5,
        "temperature": 1.0,
        "include_skill_templates_in_augmentation": False,
        "skill_selection_temperature": 0.2,
        "skill_candidate_k": 20,
        "min_llm_skills": 1,
        "max_llm_skills": 5,
        "skill_selection_planner_max_chars": 3500,
        "ensemble_skill_plans": {
            "enabled": False,
            "count": 3,
            "parallel": True,
            "max_parallel_workers": 3,
            "tail_recursion_limit": 600,
            "branch_log_dir": "",
            "branch_log_subdir": "solvita_ensemble",
            "diversity": {"temperature_delta": [0.0, 0.04, -0.04]},
        },
    }


def _load_solver_network_defaults() -> Dict[str, Any]:
    """Load ``config/solver_network.yaml`` and resolve ``graph_dir``."""
    repo_root = _REPO_ROOT
    path = repo_root / "config" / "solver_network.yaml"
    if not path.is_file():
        return _fallback_solver_network_defaults(repo_root)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sn = data.get("solver_network")
    if not isinstance(sn, dict):
        return _fallback_solver_network_defaults(repo_root)
    out: Dict[str, Any] = dict(sn)
    gd = out.get("graph_dir", "")
    if isinstance(gd, str) and gd.strip():
        out["graph_dir"] = _resolve_repo_path(repo_root, gd)
    else:
        out["graph_dir"] = ""
    fb = _fallback_solver_network_defaults(repo_root)
    fe = dict(fb.get("ensemble_skill_plans") or {})
    ens = out.get("ensemble_skill_plans")
    if not isinstance(ens, dict):
        out["ensemble_skill_plans"] = fe
    else:
        out["ensemble_skill_plans"] = {**fe, **ens}
        div_d = fe.get("diversity") if isinstance(fe.get("diversity"), dict) else {}
        div_u = ens.get("diversity") if isinstance(ens.get("diversity"), dict) else {}
        if div_d or div_u:
            out["ensemble_skill_plans"]["diversity"] = {**div_d, **div_u}
    return out


def _fallback_trainable_memory_defaults(repo_root: Path) -> Dict[str, Any]:
    """Used when ``config/trainable_memory.yaml`` is missing."""
    return {
        "enabled": False,
        "hacker_enabled": True,
        "oracle_enabled": True,
        "data_dir": _resolve_repo_path(repo_root, "artifacts/trainable_memory"),
        "plan_top_k": 3,
        "solve_top_k": 3,
        "test_top_k": 3,
        "hack_top_k": 3,
        "oracle_top_k": 3,
        "oracle_memory_mode": "off",
        "oracle_memory_snapshot_id": "",
    }


def _load_trainable_memory_defaults() -> Dict[str, Any]:
    """Load ``config/trainable_memory.yaml`` and resolve ``data_dir``."""
    repo_root = _REPO_ROOT
    path = repo_root / "config" / "trainable_memory.yaml"
    if not path.is_file():
        return _fallback_trainable_memory_defaults(repo_root)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tm = data.get("trainable_memory")
    if not isinstance(tm, dict):
        return _fallback_trainable_memory_defaults(repo_root)
    out: Dict[str, Any] = dict(tm)
    dd = out.get("data_dir", "")
    if isinstance(dd, str) and dd.strip():
        out["data_dir"] = _resolve_repo_path(repo_root, dd)
    else:
        out["data_dir"] = ""
    return out


def _fallback_codegen_defaults() -> Dict[str, Any]:
    """Used when ``config/codegen.yaml`` is missing."""
    return {
        "regenerate": False,
        "revision_mode": "patch",
    }


def _load_codegen_defaults() -> Dict[str, Any]:
    """Load ``config/codegen.yaml``."""
    repo_root = _REPO_ROOT
    path = repo_root / "config" / "codegen.yaml"
    if not path.is_file():
        return _fallback_codegen_defaults()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cg = data.get("codegen")
    if not isinstance(cg, dict):
        return _fallback_codegen_defaults()
    return dict(cg)


def _merge_runtime_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply defaults for nested runtime knobs (mutates a copy)."""
    cfg = dict(config)
    sn = cfg.get("solver_network")
    if not isinstance(sn, dict):
        sn = {}
    base = _load_solver_network_defaults()
    merged: Dict[str, Any] = {**base, **sn}
    ug = merged.get("graph_dir", "")
    if isinstance(ug, str) and ug.strip():
        merged["graph_dir"] = _resolve_repo_path(_REPO_ROOT, ug)
    else:
        merged["graph_dir"] = ""
    fe = dict(base.get("ensemble_skill_plans") or {})
    ue = merged.get("ensemble_skill_plans")
    if isinstance(ue, dict):
        merged["ensemble_skill_plans"] = {**fe, **ue}
        div_b = fe.get("diversity") if isinstance(fe.get("diversity"), dict) else {}
        div_u = ue.get("diversity") if isinstance(ue.get("diversity"), dict) else {}
        if div_b or div_u:
            merged["ensemble_skill_plans"]["diversity"] = {**div_b, **div_u}
    else:
        merged["ensemble_skill_plans"] = fe
    cfg["solver_network"] = merged

    tm = cfg.get("trainable_memory")
    if not isinstance(tm, dict):
        tm = {}
    tm_base = _load_trainable_memory_defaults()
    tm_merged: Dict[str, Any] = {**tm_base, **tm}
    udd = tm_merged.get("data_dir", "")
    if isinstance(udd, str) and udd.strip():
        tm_merged["data_dir"] = _resolve_repo_path(_REPO_ROOT, udd)
    else:
        tm_merged["data_dir"] = ""
    cfg["trainable_memory"] = tm_merged

    codegen = cfg.get("codegen")
    if not isinstance(codegen, dict):
        codegen = {}
    codegen_base = _load_codegen_defaults()
    if not isinstance(codegen_base, dict):
        codegen_base = _fallback_codegen_defaults()
    merged_codegen: Dict[str, Any] = {**codegen_base, **codegen}
    # Normalize revision mode and map regenerate -> full_regen when revision_mode is not explicitly set.
    if "revision_mode" in codegen:
        revision_mode = str((merged_codegen.get("revision_mode") or "patch")).strip().lower()
        if revision_mode not in {"patch", "full_regen"}:
            revision_mode = "patch"
        merged_codegen["revision_mode"] = revision_mode
    else:
        if bool(merged_codegen.get("regenerate")):
            merged_codegen["revision_mode"] = "full_regen"
        else:
            merged_codegen["revision_mode"] = "patch"

    cfg["codegen"] = merged_codegen
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
            tags_level2_selected=[],
            abstract_confidence=0.0,
            abstract_trace={},
        ),
        plan=PlanData(
            solution_plan={},
            algorithm_choice="",
            implementation_steps=[],
            memory_item_ids=[],
            memory_advice="",
            solver_graph_augmentation_block="",
            skill_selection_skill_ids=[],
            skill_selection_subproblem_dag={},
            skill_selection_skills_content_md="",
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

        best_solution={},
        best_tests={},
        best_phase="test",
        has_entered_hack_phase=False,

        # Metadata
        execution_log=[],
        llm_calls=0,
        prompt_tokens=0,
        completion_tokens=0,
        token_usage_source="untracked",
    )
