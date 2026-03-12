import pytest
from src.utils.reward_calculator import compute_hacker_reward
from src.utils.verdict import VerdictStatus, FailureType

def make_verdict(status: str, ftype: str):
    return {"verdict": status, "failure_type": ftype, "details": ""}


class TestRewardSpec:
    """Test the weighted reward formula:
    reward = 0.2 * valid_ratio + 0.6 * break_ratio + 0.2 * severity_bonus - compile_penalty
    """

    def _make_verdicts(self):
        """Create 10 verdicts: 5 invalid, 5 valid (3 breaks: MLE+WA+WA, 2 safe)."""
        invalids = [make_verdict(VerdictStatus.INVALID_INPUT, FailureType.NONE) for _ in range(5)]
        breaks = [
            make_verdict(VerdictStatus.VALID_AND_BREAK, FailureType.MLE),
            make_verdict(VerdictStatus.VALID_AND_BREAK, FailureType.WA),
            make_verdict(VerdictStatus.VALID_AND_BREAK, FailureType.WA),
        ]
        safes = [make_verdict(VerdictStatus.VALID_BUT_SAFE, FailureType.NONE) for _ in range(2)]
        return invalids + breaks + safes

    def test_weighted_formula_exact_match(self):
        """
        Given: 10 total, 5 valid, 3 breaks, max severity = 1.0 (MLE)
        Formula:
          valid_ratio = 5 / 10 = 0.5
          break_ratio = 3 / 5 = 0.6
          severity = 1.0
          0.2 * 0.5 + 0.6 * 0.6 + 0.2 * 1.0 = 0.1 + 0.36 + 0.2 = 0.66
        """
        verdicts = self._make_verdicts()
        reward = compute_hacker_reward(verdicts, compile_failures=0)
        assert pytest.approx(reward) == 0.66

    def test_compile_penalty_capped(self):
        """compile_penalty should not exceed MAX_COMPILE_PENALTY=0.3."""
        # Setup: 10 valid, 0 breaks -> valid_ratio=1.0, break_ratio=0.0, severity=0.0
        # raw base = 0.2 * 1.0 = 0.2
        verdicts = [make_verdict(VerdictStatus.VALID_BUT_SAFE, FailureType.NONE) for _ in range(10)]
        
        # 100 compile failures -> capped at 0.3
        # raw = 0.2 - 0.3 = -0.1
        reward_high = compute_hacker_reward(verdicts, compile_failures=100)
        
        # 3 compile failures -> exactly 0.3
        reward_low = compute_hacker_reward(verdicts, compile_failures=3)
        assert reward_high == reward_low
        assert pytest.approx(reward_high) == -0.1

    def test_no_breaks_valid_only(self):
        """If all valid inputs pass, valid_ratio=1.0, break=0, severity=0 -> 0.2"""
        verdicts = [make_verdict(VerdictStatus.VALID_BUT_SAFE, FailureType.NONE) for _ in range(5)]
        reward = compute_hacker_reward(verdicts, compile_failures=0)
        assert pytest.approx(reward) == 0.2

    def test_all_invalid_only_penalty(self):
        """If no valid inputs at all, valid_ratio=0 -> 0.0 base"""
        verdicts = [make_verdict(VerdictStatus.INVALID_INPUT, FailureType.NONE) for _ in range(5)]
        reward = compute_hacker_reward(verdicts, compile_failures=0)
        assert reward == 0.0

    def test_gen_failed_empty_verdicts(self):
        """If router returns nothing, empty verdicts -> 0.0 base."""
        reward = compute_hacker_reward([], compile_failures=0)
        assert reward == 0.0

    def test_clipping_upper_bound(self):
        """Ensure values > 1.0 get clipped to 1.0. (Though mathematical max is 1.0 anyway)."""
        verdicts = [make_verdict(VerdictStatus.VALID_AND_BREAK, FailureType.MLE)]
        # valid_ratio=1.0, break_ratio=1.0, severity=1.0 -> 0.2+0.6+0.2 = 1.0
        reward = compute_hacker_reward(verdicts)
        assert pytest.approx(reward) == 1.0

    def test_clipping_lower_bound(self):
        """Ensure clipping works at lower bound when penalty is huge."""
        verdicts = []  # 0 reward base
        reward = compute_hacker_reward(verdicts, compile_failures=100)
        # 0.0 - 0.3 = -0.3 
        assert pytest.approx(reward) == -0.3
