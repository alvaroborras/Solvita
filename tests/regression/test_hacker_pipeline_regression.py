"""
T5.1 Hacker Pipeline Architecture Regression Tests
===================================================

Full end-to-end regression suite for the v2 Hacker System refactoring.
All external dependencies (LLM, C++ compiler, subprocess) are fully mocked.

Coverage targets (from genesis/v2/05_TASKS.md T5.1 acceptance criteria):
  Analyst → Router → Generator → Execution → Reward (settlement)
  AND all cascading fallback paths (semantic → stress degrade).

Scenario matrix:
  Scenario 1: "Happy path – BREAK"
      Analyst emits bug_class → Router routes "semantic" → Execution finds WA →
      hack_test returns BREAK → settle_hacker_memory computes real reward.

  Scenario 2: "Safe path – SAFE"
      Same pipeline but all verdicts are VALID_BUT_SAFE → returns SAFE.

  Scenario 3: "All generation fails – GEN_FAILED"
      Router returns ("failed", "", [...]) → hack_test returns GEN_FAILED →
      validator_rejection_reasons is a structured list.

  Scenario 4: "Cascading fallback – Semantic→Stress degrade"
      cascading_execution_router itself is exercised (not just mocked at boundary).
      Semantic generator always produces bad code (compile fail),
      after 3 retries router degrades to Stress which succeeds.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from src.nodes.hack_test import hack_test_node
from src.nodes.settle_hacker_memory import settle_hacker_memory
from src.utils.verdict import VerdictStatus, FailureType
from src.utils.reward_calculator import compute_hacker_reward


# ─────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def base_state():
    return {
        "problem": {
            "description": "Given N integers, find the max sum subarray.",
            "constraints": {"N": "1..1e5", "A_i": "-1e9..1e9"},
            "canonical": {"id": "P42"},
        },
        "solution": {
            "code": "int main() { /* ... */ }",
            "executable_path": "/tmp/sol.exe",
        },
        "config": {"k": 3},
        "tests": {"validator_exe": "/tmp/val.exe"},
        "raw_problem": {"problem_id": "P42"},
        "hack_round": 1,
    }


@pytest.fixture
def common_mocks(monkeypatch):
    """Patch everything external to the Hacker pipeline boundary."""
    monkeypatch.setattr("src.nodes.hack_test.Path.exists", lambda self: True)
    monkeypatch.setattr("src.nodes.hack_test.UnifiedLLMClient", MagicMock())
    mock_mem = MagicMock()
    mock_mem.get_injection.return_value = ("use edge-case inputs", ["mem_id_1"])
    monkeypatch.setattr("src.nodes.hack_test.MemoryClient", lambda **kw: mock_mem)
    monkeypatch.setattr(
        "src.nodes.hack_test.run_code_analyst",
        lambda *a, **k: {
            "bug_class": "overflow",
            "confidence": "high",
            "evidence": "N=1e9 triggers int overflow in sum accumulation.",
            "suggested_route": "semantic",
            "suggested_fix": None,
        },
    )
    return mock_mem


# ─────────────────────────────────────────────
# Scenario 1: BREAK – target bug found
# ─────────────────────────────────────────────

class TestScenario1Break:
    """Full pipeline: Analyst → semantic Router → Execution → BREAK → Settlement."""

    def test_hack_test_returns_break_state(self, base_state, common_mocks, monkeypatch):
        monkeypatch.setattr(
            "src.nodes.hack_test.cascading_execution_router",
            lambda *a, **k: ("semantic", "5\n1 2 3 4 5\n", ["Router: Semantic OK."]),
        )
        wa_verdict = {
            "verdict": VerdictStatus.VALID_AND_BREAK.value,
            "failure_type": FailureType.WA.value,
            "details": "Expected 15, got 13.",
        }
        monkeypatch.setattr("src.nodes.hack_test.evaluate_verdict", lambda *a, **k: wa_verdict)
        monkeypatch.setattr("src.nodes.hack_test.run_program", lambda *a, **k: (0, "13\n", ""))

        result = hack_test_node(base_state)

        # State contract assertions (all v2 fields)
        assert result["hack_result"] == "BREAK"
        assert result["hack_passed"] is False
        assert result["generator_route_used"] == "semantic"
        assert result["hack_failure_type"] == FailureType.WA.value
        assert len(result["hack_failures"]) == 1
        assert result["hack_failures"][0]["type"] == FailureType.WA.value
        # sentinel reward before settlement
        assert result["hacker_reward"] == 0.0
        # raw evidence exposed for settlement
        assert "sandbox_verdicts" in result
        assert "compile_failures" in result
        assert result["compile_failures"] == 0

    def test_settlement_computes_real_reward_on_break(self, base_state, monkeypatch):
        """T4.2: settle_hacker_memory reads sandbox_verdicts and rewrites hacker_reward."""
        state = dict(base_state)
        state.update({
            "hacker_memory_item_ids": ["mem_id_1"],
            "sandbox_verdicts": [
                {"verdict": VerdictStatus.VALID_AND_BREAK.value, "failure_type": FailureType.WA.value}
            ],
            "compile_failures": 0,
            "analyst_report": {"bug_class": "overflow", "confidence": "high"},
            "generator_route_used": "semantic",
            "hack_result": "BREAK",
            "hack_failure_type": FailureType.WA.value,
            "hack_round": 1,
        })

        mock_mem = MagicMock()
        mock_mem.featurizer = None
        monkeypatch.setattr("src.nodes.settle_hacker_memory.MemoryClient", lambda **kw: mock_mem)

        result = settle_hacker_memory(state)

        # Real reward: valid_ratio=1.0, break_ratio=1.0, severity=0.4(WA) → 0.2+0.6+0.08=0.88
        assert result["hacker_reward"] == pytest.approx(0.88)
        assert mock_mem.log_event.call_count == 1
        obs = mock_mem.log_event.call_args[0][0]
        assert obs.extra["hack_result"] == "BREAK"
        assert obs.extra["generator_route"] == "semantic"
        assert obs.failure_type == FailureType.WA.value


# ─────────────────────────────────────────────
# Scenario 2: SAFE – no bug found
# ─────────────────────────────────────────────

class TestScenario2Safe:
    """Full pipeline where target withstands all generated inputs."""

    def test_hack_test_returns_safe_state(self, base_state, common_mocks, monkeypatch):
        monkeypatch.setattr(
            "src.nodes.hack_test.cascading_execution_router",
            lambda *a, **k: ("stress", "3\n1 2 3\n", ["Router: Stress OK."]),
        )
        safe_verdict = {
            "verdict": VerdictStatus.VALID_BUT_SAFE.value,
            "failure_type": FailureType.NONE.value,
            "details": "",
        }
        monkeypatch.setattr("src.nodes.hack_test.evaluate_verdict", lambda *a, **k: safe_verdict)
        monkeypatch.setattr("src.nodes.hack_test.run_program", lambda *a, **k: (0, "6\n", ""))

        result = hack_test_node(base_state)

        assert result["hack_result"] == "SAFE"
        assert result["hack_passed"] is True
        assert result["generator_route_used"] == "stress"
        assert result["hack_failure_type"] == "NONE"
        assert result["hack_failures"] == []
        assert result["hacker_reward"] == 0.0  # sentinel; settlement will compute ~0.2

    def test_settlement_computes_reward_on_safe(self, base_state, monkeypatch):
        state = dict(base_state)
        state.update({
            "hacker_memory_item_ids": ["mem_id_1"],
            "sandbox_verdicts": [
                {"verdict": VerdictStatus.VALID_BUT_SAFE.value, "failure_type": FailureType.NONE.value}
            ],
            "compile_failures": 0,
            "analyst_report": {"bug_class": "overflow", "confidence": "high"},
            "generator_route_used": "stress",
            "hack_result": "SAFE",
            "hack_failure_type": "NONE",
            "hack_round": 1,
        })
        mock_mem = MagicMock()
        mock_mem.featurizer = None
        monkeypatch.setattr("src.nodes.settle_hacker_memory.MemoryClient", lambda **kw: mock_mem)

        result = settle_hacker_memory(state)

        # valid_ratio=1.0, break=0, severity=0 → 0.2 * 1 = 0.2
        assert result["hacker_reward"] == pytest.approx(0.2)
        obs = mock_mem.log_event.call_args[0][0]
        assert obs.failure_type is None  # SAFE → no failure type


# ─────────────────────────────────────────────
# Scenario 3: GEN_FAILED – all generation paths exhausted
# ─────────────────────────────────────────────

class TestScenario3GenFailed:
    """Pipeline where router exhausts all retries and returns 'failed'."""

    def test_hack_test_returns_gen_failed_state(self, base_state, common_mocks, monkeypatch):
        monkeypatch.setattr(
            "src.nodes.hack_test.cascading_execution_router",
            lambda *a, **k: (
                "failed",
                "",
                [
                    "Router: Semantic attempt 1 failed (compile error)",
                    "Router: Semantic attempt 2 failed (compile error)",
                    "Router: Semantic attempt 3 failed (compile error)",
                    "Router: Stress generator fallback also failed (empty output)",
                ],
            ),
        )
        result = hack_test_node(base_state)

        assert result["hack_result"] == "GEN_FAILED"
        assert result["hack_passed"] is True
        assert result["hacker_reward"] == -1.0  # GEN_FAILED returns hard -1.0
        assert result["generator_route_used"] == "failed"
        assert result["hack_failure_type"] == "NONE"

        # validator_rejection_reasons must be structured list of dicts
        reasons = result["validator_rejection_reasons"]
        assert isinstance(reasons, list)
        assert len(reasons) > 0
        for r in reasons:
            assert isinstance(r, dict)
            assert "stage" in r
            assert "reason" in r


# ─────────────────────────────────────────────
# Scenario 4: Cascading Router fallback path
# ─────────────────────────────────────────────

class TestScenario4CascadingFallback:
    """
    Exercises cascading_execution_router directly (not mocked at boundary).
    Semantic generator always fails compile → after 3 retries, falls back to Stress.
    """

    def test_router_degrades_semantic_to_stress(self, base_state, monkeypatch):
        """
        Given: Semantic generator always fails to compile.
        When: cascading_execution_router is invoked with max_retries=3.
        Then: route returns 'stress' (not 'semantic' or 'failed').
        """
        # Semantic generator: always produces broken C++ code
        monkeypatch.setattr(
            "src.nodes.cascading_router.generate_semantic_test_program",
            lambda *a, **k: "NOT VALID C++",
        )
        # Stress generator: produces valid code 
        monkeypatch.setattr(
            "src.nodes.cascading_router.generate_stress_test_program",
            lambda *a, **k: "VALID C++",
        )
        # execute_generator_and_validate: fail for semantic, succeed for stress
        call_count = {"n": 0}
        def fake_execute(cpp_source, validator_exe, problem_limits):
            if cpp_source == "NOT VALID C++":
                return False, "", "Compilation Failed: syntax error"
            return True, "3\n1 2 3\n", ""
        monkeypatch.setattr(
            "src.nodes.cascading_router.execute_generator_and_validate",
            fake_execute,
        )

        from src.nodes.cascading_router import cascading_execution_router
        llm = MagicMock()
        analyst_report = {"suggested_route": "semantic"}
        route, inp, log = cascading_execution_router(
            base_state, llm, analyst_report, max_retries=3
        )

        assert route == "stress", f"Expected stress fallback, got '{route}'"
        assert inp.strip() != ""
        # Verify 3 semantic attempts were logged before degradation
        semantic_attempts = [l for l in log if "Semantic generation attempt" in l]
        assert len(semantic_attempts) == 3
        downgrade_logged = any("Downgrading to Stress" in l for l in log)
        assert downgrade_logged

    def test_router_anti_hash_degrades_to_semantic(self, base_state, monkeypatch):
        """
        Given: anti_hash suggested but fails → falls back to semantic which succeeds.
        """
        monkeypatch.setattr(
            "src.nodes.cascading_router.generate_anti_hash_test_program",
            lambda *a, **k: "BAD HASH CPP",
        )
        monkeypatch.setattr(
            "src.nodes.cascading_router.generate_semantic_test_program",
            lambda *a, **k: "GOOD SEMANTIC CPP",
        )

        def fake_execute(cpp_source, validator_exe, problem_limits):
            if cpp_source == "BAD HASH CPP":
                return False, "", "Compilation Failed: hash logic broken"
            return True, "1\n42\n", ""

        monkeypatch.setattr(
            "src.nodes.cascading_router.execute_generator_and_validate",
            fake_execute,
        )

        from src.nodes.cascading_router import cascading_execution_router
        llm = MagicMock()
        analyst_report = {"suggested_route": "anti_hash"}
        route, inp, log = cascading_execution_router(
            base_state, llm, analyst_report, max_retries=3
        )

        assert route == "semantic"
        assert "42" in inp
        downgraded = any("Downgrading to Semantic" in l for l in log)
        assert downgraded


# ─────────────────────────────────────────────
# Reward math cross-check (integration with real compute_hacker_reward)
# ─────────────────────────────────────────────

class TestRewardIntegration:
    """Validates that the reward formula produces expected values end-to-end."""

    def test_spec_example_weighted_formula(self):
        """
        From genesis/v2/05_TASKS.md T4.1 spec example:
          total=10, valid=5 (3 breaks: MLE+WA+WA, 2 safe), invalid=5
          0.2*(5/10) + 0.6*(3/5) + 0.2*max(MLE=1.0, WA=0.4, WA=0.4) = 0.66
        """
        verdicts = (
            [{"verdict": VerdictStatus.INVALID_INPUT.value, "failure_type": FailureType.NONE.value}] * 5
            + [{"verdict": VerdictStatus.VALID_AND_BREAK.value, "failure_type": FailureType.MLE.value}]
            + [{"verdict": VerdictStatus.VALID_AND_BREAK.value, "failure_type": FailureType.WA.value}] * 2
            + [{"verdict": VerdictStatus.VALID_BUT_SAFE.value, "failure_type": FailureType.NONE.value}] * 2
        )
        reward = compute_hacker_reward(verdicts, compile_failures=0)
        assert reward == pytest.approx(0.66)

    def test_full_break_max_reward(self):
        """1 input, 1 MLE break → max formula score = 0.2+0.6+0.2 = 1.0"""
        verdicts = [{"verdict": VerdictStatus.VALID_AND_BREAK.value, "failure_type": FailureType.MLE.value}]
        assert compute_hacker_reward(verdicts) == pytest.approx(1.0)

    def test_compile_penalty_caps(self):
        """100 compile failures → penalty capped at 0.3, valid_ratio=0 → total -0.3"""
        reward = compute_hacker_reward([], compile_failures=100)
        assert reward == pytest.approx(-0.3)
