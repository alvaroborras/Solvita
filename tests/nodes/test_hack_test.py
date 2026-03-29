import pytest
from unittest.mock import MagicMock
from src.nodes.hack_test import hack_test_node
from src.utils.verdict import VerdictStatus, FailureType
from src.hacker.runtime import execute_hack_candidate

@pytest.fixture
def base_mocks(monkeypatch):
    """Set up common mocks for all hack_test_node tests."""
    monkeypatch.setattr("src.nodes.hack_test.Path.exists", lambda self: True)
    monkeypatch.setattr("src.nodes.hack_test.UnifiedLLMClient", MagicMock())
    mock_mem = MagicMock()
    mock_mem.get_injection.return_value = ("advice", ["id1"])
    monkeypatch.setattr("src.nodes.hack_test.MemoryClient", lambda **kw: mock_mem)
    monkeypatch.setattr("src.nodes.hack_test.run_code_analyst", lambda *a, **k: {"bug_class": "overflow"})
    return mock_mem

@pytest.fixture
def mock_state():
    return {
        "problem": {"description": "test", "constraints": {}},
        "solution": {"code": "int main(){}", "executable_path": "dummy.exe"},
        "config": {},
        "tests": {"validator_exe": "val.exe"},
        "raw_problem": {},
    }

# ---- Test 1: Router total failure → GEN_FAILED state ----

def test_router_failure_returns_structured_rejections(mock_state, base_mocks, monkeypatch):
    """GEN_FAILED path: validator_rejection_reasons should be a list of dicts."""
    monkeypatch.setattr(
        "src.nodes.hack_test.cascading_execution_router",
        lambda *a, **k: ("failed", "", ["Router: Anti-Hash failed (compile error)", "Router: Semantic failed (validator rejected)"])
    )
    result = hack_test_node(mock_state)

    assert result["hack_result"] == "GEN_FAILED"
    assert result["generator_route_used"] == "failed"
    assert result["hack_failure_type"] == "NONE"
    assert result["hack_passed"] is True
    assert result["hacker_reward"] == -1.0
    # validator_rejection_reasons must be a list of dicts, not strings
    reasons = result["validator_rejection_reasons"]
    assert isinstance(reasons, list)
    assert len(reasons) > 0
    assert isinstance(reasons[0], dict)
    assert "stage" in reasons[0] and "reason" in reasons[0]

# ---- Test 2: Target breaks → BREAK state with all new fields ----

def test_target_break_writes_all_new_state_fields(mock_state, base_mocks, monkeypatch):
    """BREAK path: all three new state contract fields must be written correctly."""
    monkeypatch.setattr(
        "src.nodes.hack_test.cascading_execution_router",
        lambda *a, **k: ("semantic", "100\n", ["log"])
    )
    mock_verdict = {"verdict": VerdictStatus.VALID_AND_BREAK.value, "failure_type": FailureType.WA.value, "details": ""}
    monkeypatch.setattr("src.nodes.hack_test.evaluate_verdict", lambda *a, **k: mock_verdict)
    monkeypatch.setattr("src.nodes.hack_test.run_program", lambda *a, **k: (0, "99\n", ""))

    result = hack_test_node(mock_state)

    assert result["hack_passed"] is False
    # hacker_reward is a sentinel 0.0; real reward is computed in settle_hacker_memory (T4.2)
    assert result["hacker_reward"] == 0.0
    assert result["hack_result"] == "BREAK"                   # ← new field
    assert result["generator_route_used"] == "semantic"        # ← new field
    assert result["hack_failure_type"] == FailureType.WA.value # ← new field
    assert len(result["hack_failures"]) == 1

# ---- Test 3: Target passes safely → SAFE state ----

def test_target_safe_writes_all_new_state_fields(mock_state, base_mocks, monkeypatch):
    """SAFE path: all three new state contract fields must be SAFE/NONE."""
    monkeypatch.setattr(
        "src.nodes.hack_test.cascading_execution_router",
        lambda *a, **k: ("stress", "5\n1 2 3 4 5\n", ["log"])
    )
    safe_verdict = {"verdict": VerdictStatus.VALID_BUT_SAFE.value, "failure_type": FailureType.NONE.value, "details": ""}
    monkeypatch.setattr("src.nodes.hack_test.evaluate_verdict", lambda *a, **k: safe_verdict)
    monkeypatch.setattr("src.nodes.hack_test.run_program", lambda *a, **k: (0, "correct\n", ""))

    result = hack_test_node(mock_state)

    assert result["hack_passed"] is True
    # hacker_reward is a sentinel 0.0; real reward is computed in settle_hacker_memory (T4.2)
    assert result["hacker_reward"] == 0.0
    assert result["hack_result"] == "SAFE"                     # ← new field
    assert result["generator_route_used"] == "stress"          # ← new field
    assert result["hack_failure_type"] == "NONE"               # ← new field

# ---- Test 4: TLE via run_program returning code 124 ----

def test_target_tle_via_run_program(mock_state, base_mocks, monkeypatch):
    """Coverage for TLE path through unified run_program (returncode 124)."""
    monkeypatch.setattr(
        "src.nodes.hack_test.cascading_execution_router",
        lambda *a, **k: ("semantic", "100\n", ["log"])
    )
    tle_verdict = {"verdict": VerdictStatus.VALID_AND_BREAK.value, "failure_type": FailureType.TLE.value, "details": "TLE"}
    monkeypatch.setattr("src.nodes.hack_test.evaluate_verdict", lambda *a, **k: tle_verdict)
    # Simulate run_program returning TLE signal
    monkeypatch.setattr("src.nodes.hack_test.run_program", lambda *a, **k: (124, "", "Time Limit Exceeded"))

    result = hack_test_node(mock_state)

    assert result["hack_result"] == "BREAK"
    assert result["hack_failure_type"] == FailureType.TLE.value

# ---- Test 5: Checker branch (run_checker called) ----

def test_checker_branch_called(mock_state, base_mocks, monkeypatch):
    """Coverage: verify checker is invoked when checker_exe is provided."""
    mock_state["tests"]["checker_exe"] = "checker.exe"
    monkeypatch.setattr(
        "src.nodes.hack_test.cascading_execution_router",
        lambda *a, **k: ("anti_hash", "input\n", ["log"])
    )
    monkeypatch.setattr("src.nodes.hack_test.run_program", lambda *a, **k: (0, "output\n", ""))
    mock_checker = MagicMock(return_value=(False, "WA: expected 1 got 2"))
    monkeypatch.setattr("src.nodes.hack_test.run_checker", mock_checker)
    wa_verdict = {"verdict": VerdictStatus.VALID_AND_BREAK.value, "failure_type": FailureType.WA.value, "details": ""}
    monkeypatch.setattr("src.nodes.hack_test.evaluate_verdict", lambda *a, **k: wa_verdict)

    result = hack_test_node(mock_state)

    assert mock_checker.called
    assert result["hack_result"] == "BREAK"

# ---- Test 6: System exception in run_program ----

def test_execution_exception_handled(mock_state, base_mocks, monkeypatch):
    """Coverage: exception in run_program is caught and added as System Error failure."""
    monkeypatch.setattr(
        "src.nodes.hack_test.cascading_execution_router",
        lambda *a, **k: ("semantic", "100\n", ["log"])
    )
    monkeypatch.setattr("src.nodes.hack_test.run_program", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    result = hack_test_node(mock_state)

    assert any(f.get("type") == "System Error" for f in result["hack_failures"])


def test_execute_hack_candidate_uses_expected_output_without_checker(monkeypatch, tmp_path):
    exe_path = tmp_path / "sol.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr("src.hacker.runtime.run_program", lambda *a, **k: (0, "13\n", ""))

    result = execute_hack_candidate(
        exe_path=exe_path,
        generated_input="5\n1 2 3 4 5\n",
        expected_output="15\n",
        checker_exe=None,
    )

    assert result["sandbox_verdicts"][0]["verdict"] == VerdictStatus.VALID_AND_BREAK.value
    assert result["sandbox_verdicts"][0]["failure_type"] == FailureType.WA.value
    assert result["hack_failures"][0]["expected"] == "15"
