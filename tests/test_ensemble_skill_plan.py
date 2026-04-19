"""Tests for ensemble skill-plan branch comparison and orchestration."""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.nodes.best_solution import is_better_ensemble_branch
from src.graph.workflow import (
    ENSEMBLE_CASE_LOG_DIR_KEY,
    ENSEMBLE_PRE_LOG_SINK_KEY,
    setup_ensemble_case_logging,
    teardown_ensemble_pre_log_sink,
)
from src.nodes.solver_skill_plan_ensemble import (
    _resolve_branch_log_file,
    solver_skill_plan_ensemble_node,
)


def test_is_better_ensemble_branch_pass_rate():
    a = {"pass_rate": 0.8, "passed_tests": 3, "total_tests": 5, "branch_elapsed_s": 1.0, "branch_index": 0}
    b = {"pass_rate": 0.5, "passed_tests": 4, "total_tests": 5, "branch_elapsed_s": 0.1, "branch_index": 1}
    assert is_better_ensemble_branch(a, b)
    assert not is_better_ensemble_branch(b, a)


def test_is_better_ensemble_branch_passed_tests_tiebreak():
    a = {"pass_rate": 0.5, "passed_tests": 3, "total_tests": 5, "branch_elapsed_s": 1.0, "branch_index": 0}
    b = {"pass_rate": 0.5, "passed_tests": 2, "total_tests": 5, "branch_elapsed_s": 0.1, "branch_index": 1}
    assert is_better_ensemble_branch(a, b)


def test_is_better_ensemble_branch_full_pass_faster_wins():
    a = {"pass_rate": 1.0, "passed_tests": 5, "total_tests": 5, "branch_elapsed_s": 2.0, "branch_index": 1}
    b = {"pass_rate": 1.0, "passed_tests": 5, "total_tests": 5, "branch_elapsed_s": 5.0, "branch_index": 0}
    assert is_better_ensemble_branch(a, b)


def test_is_better_ensemble_branch_index_tiebreak():
    a = {"pass_rate": 1.0, "passed_tests": 5, "total_tests": 5, "branch_elapsed_s": 1.0, "branch_index": 1}
    b = {"pass_rate": 1.0, "passed_tests": 5, "total_tests": 5, "branch_elapsed_s": 1.0, "branch_index": 2}
    assert is_better_ensemble_branch(a, b)


def test_solver_skill_plan_ensemble_picks_higher_pass_rate():
    base_state = {
        "raw_problem": {"id": "p1"},
        "config": {
            "solver_network": {
                "enabled": True,
                "graph_dir": "",
                "ensemble_skill_plans": {
                    "enabled": True,
                    "count": 2,
                    "parallel": False,
                    "tail_recursion_limit": 400,
                },
            },
            "_token_usage_accumulator": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "llm_calls": 2,
                "source_counts": {"api": 1, "estimated": 0, "mixed": 0},
            },
        },
        "problem": {"description": "x", "canonical": {}, "public_tests": []},
        "plan": {},
        "solution": {"code": ""},
        "tests": {"generated_tests": [], "pass_rate": 0.0, "passed_tests": 0, "total_tests": 0},
        "messages": [],
        "execution_log": [],
        "llm_calls": 3,
        "iteration": 0,
        "status": "pending",
        "current_phase": "CODEGEN",
    }

    def fake_run_skill(state):
        bid = int((state.get("config") or {}).get("solver_network", {}).get("ensemble_branch_id", 0))
        return {"plan": {"algorithm_choice": f"b{bid}"}, "execution_log": [], "llm_calls": 0}

    def fake_invoke(st, inv_cfg):
        bid = int((st.get("config") or {}).get("solver_network", {}).get("ensemble_branch_id", 0))
        pr = 0.4 if bid == 0 else 0.9
        return {
            "solution": {"code": f"//{bid}", "compilation_success": True},
            "tests": {
                "generated_tests": [{"input": "1", "expected_output": "1"}],
                "pass_rate": pr,
                "passed_tests": int(10 * pr),
                "total_tests": 10,
            },
            "plan": dict(st.get("plan") or {}),
            "feedback": {},
            "iteration": 1,
            "status": "success",
            "hack_round": 0,
            "hack_passed": True,
            "hack_failures": [],
            "hack_result": "SAFE",
            "generator_route_used": "",
            "hack_failure_type": "NONE",
            "generator_failure_kind": "",
            "generator_failure_reason": "",
            "messages": [],
            "current_phase": "HACKER",
            "solver_network_oneshot_spent": True,
            "best_solution": {},
            "best_tests": {},
            "best_phase": "hack",
            "has_entered_hack_phase": True,
            "analyst_report": {},
            "validator_rejection_reasons": [],
            "hacker_memory_item_ids": [],
            "oracle_memory_item_ids": [],
            "config": copy.deepcopy(st.get("config") or {}),
            "llm_calls": 5 + bid,
        }

    mock_tail = MagicMock()
    mock_tail.invoke.side_effect = fake_invoke

    with patch(
        "src.nodes.solver_skill_plan_ensemble.run_skill_plan_once",
        side_effect=fake_run_skill,
    ), patch(
        "src.nodes.solver_skill_plan_ensemble._get_codegen_hacker_tail",
        return_value=mock_tail,
    ):
        out = solver_skill_plan_ensemble_node(base_state)

    assert out["solution"]["code"] == "//1"
    assert out["tests"]["pass_rate"] == pytest.approx(0.9)
    assert out["config"]["ensemble_trace"]["winner_branch_index"] == 1
    assert mock_tail.invoke.call_count == 2


def test_solver_skill_plan_ensemble_parallel_thread_pool_invokes_tail():
    """parallel=true uses ThreadPoolExecutor; two branches overlap before returning (barrier)."""
    invoke_barrier = threading.Barrier(2)

    base_state = {
        "raw_problem": {"id": "p1"},
        "config": {
            "solver_network": {
                "enabled": True,
                "graph_dir": "",
                "ensemble_skill_plans": {
                    "enabled": True,
                    "count": 2,
                    "parallel": True,
                    "max_parallel_workers": 2,
                    "tail_recursion_limit": 400,
                },
            },
            "_token_usage_accumulator": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "llm_calls": 2,
                "source_counts": {"api": 1, "estimated": 0, "mixed": 0},
            },
        },
        "problem": {"description": "x", "canonical": {}, "public_tests": []},
        "plan": {},
        "solution": {"code": ""},
        "tests": {"generated_tests": [], "pass_rate": 0.0, "passed_tests": 0, "total_tests": 0},
        "messages": [],
        "execution_log": [],
        "llm_calls": 3,
        "iteration": 0,
        "status": "pending",
        "current_phase": "CODEGEN",
    }

    def fake_run_skill(state):
        bid = int((state.get("config") or {}).get("solver_network", {}).get("ensemble_branch_id", 0))
        return {"plan": {"algorithm_choice": f"b{bid}"}, "execution_log": [], "llm_calls": 0}

    def fake_invoke(st, inv_cfg):
        bid = int((st.get("config") or {}).get("solver_network", {}).get("ensemble_branch_id", 0))
        invoke_barrier.wait(timeout=10)
        pr = 0.3 if bid == 0 else 0.95
        return {
            "solution": {"code": f"//{bid}", "compilation_success": True},
            "tests": {
                "generated_tests": [{"input": "1", "expected_output": "1"}],
                "pass_rate": pr,
                "passed_tests": int(10 * pr),
                "total_tests": 10,
            },
            "plan": dict(st.get("plan") or {}),
            "feedback": {},
            "iteration": 1,
            "status": "success",
            "hack_round": 0,
            "hack_passed": True,
            "hack_failures": [],
            "hack_result": "SAFE",
            "generator_route_used": "",
            "hack_failure_type": "NONE",
            "generator_failure_kind": "",
            "generator_failure_reason": "",
            "messages": [],
            "current_phase": "HACKER",
            "solver_network_oneshot_spent": True,
            "best_solution": {},
            "best_tests": {},
            "best_phase": "hack",
            "has_entered_hack_phase": True,
            "analyst_report": {},
            "validator_rejection_reasons": [],
            "hacker_memory_item_ids": [],
            "oracle_memory_item_ids": [],
            "config": copy.deepcopy(st.get("config") or {}),
            "llm_calls": 5 + bid,
        }

    mock_tail = MagicMock()
    mock_tail.invoke.side_effect = fake_invoke

    with patch(
        "src.nodes.solver_skill_plan_ensemble.run_skill_plan_once",
        side_effect=fake_run_skill,
    ), patch(
        "src.nodes.solver_skill_plan_ensemble._get_codegen_hacker_tail",
        return_value=mock_tail,
    ):
        out = solver_skill_plan_ensemble_node(base_state)

    assert out["solution"]["code"] == "//1"
    assert out["config"]["ensemble_trace"]["winner_branch_index"] == 1
    assert mock_tail.invoke.call_count == 2


def test_setup_ensemble_case_logging_writes_pre_file(tmp_path):
    from loguru import logger

    st = {
        "raw_problem": {"problem_id": "P99_Z"},
        "config": {
            "benchmark_output_dir": str(tmp_path),
            "solver_network": {
                "enabled": True,
                "ensemble_skill_plans": {"enabled": True, "count": 2},
            },
        },
    }
    setup_ensemble_case_logging(st)
    case_dir = Path(st["config"][ENSEMBLE_CASE_LOG_DIR_KEY])
    assert case_dir.is_dir()
    logger.info("probe_line_for_pre_ensemble_sink")
    teardown_ensemble_pre_log_sink(st["config"])
    text = (case_dir / "00_pre_ensemble.log").read_text(encoding="utf-8")
    assert "probe_line_for_pre_ensemble_sink" in text
    assert ENSEMBLE_PRE_LOG_SINK_KEY not in st["config"]


def test_resolve_branch_log_file_prefers_ensemble_case_dir(tmp_path):
    case = tmp_path / "1622_A_case"
    case.mkdir()
    base = {
        "raw_problem": {"problem_id": "1622_A"},
        "config": {
            "benchmark_output_dir": str(tmp_path),
            "_ensemble_case_log_dir": str(case),
        },
    }
    p = _resolve_branch_log_file(base, 1)
    assert p == case / "branch_01.log"


def test_resolve_branch_log_file_uses_benchmark_output_dir(tmp_path):
    base = {
        "raw_problem": {"problem_id": "1575_A. Demo"},
        "config": {"benchmark_output_dir": str(tmp_path)},
    }
    p = _resolve_branch_log_file(base, 1)
    assert p is not None
    assert p.parent.name == "solvita_ensemble"
    assert p.name == "1575_A._Demo_b1.log"


def test_resolve_branch_log_file_branch_log_dir_fallback(tmp_path):
    root = tmp_path / "custom"
    root.mkdir()
    base = {
        "raw_problem": {},
        "config": {
            "solver_network": {
                "ensemble_skill_plans": {
                    "branch_log_dir": str(root),
                    "branch_log_subdir": "ensemble_logs",
                }
            }
        },
    }
    p = _resolve_branch_log_file(base, 0)
    assert p == root.resolve() / "logs" / "ensemble_logs" / "unknown_b0.log"


def test_solver_skill_plan_ensemble_skips_when_disabled():
    st = {
        "config": {"solver_network": {"enabled": True, "ensemble_skill_plans": {"enabled": False}}},
        "llm_calls": 1,
    }
    assert solver_skill_plan_ensemble_node(st) == {}
