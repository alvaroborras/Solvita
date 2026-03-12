"""
T4.1 Continuous Reward Calculator for the Hacker System.

Mathematical contract (from genesis/v2/05_TASKS.md T4.1):
    reward = 0.2 * valid_ratio + 0.6 * break_ratio + 0.2 * severity_bonus - compile_penalty
    clipped to [-1.0, 1.0]

Definitions:
    valid_ratio  = count(VALID_INPUTS) / max(1, count(ALL_INPUTS))
    break_ratio  = count(VALID_AND_BREAK) / max(1, count(VALID_INPUTS))
                   INVALID_INPUT verdicts do NOT count in the denominator.
    severity_bonus = max severity among VALID_AND_BREAK failures
                   severity order: MLE(1.0) > TLE(0.8) > RE(0.6) > WA(0.4)
                   Only the single highest value is added.
    compile_penalty = (number of compile failures) * per_compile_penalty
                   Default per_compile_penalty = -0.1, capped at -0.3.
"""
from typing import List, Dict, Any
from src.utils.verdict import VerdictStatus, FailureType

# Severity weights per failure type (MLE > TLE > RE > WA)
SEVERITY_WEIGHTS: Dict[str, float] = {
    FailureType.MLE: 1.0,
    FailureType.TLE: 0.8,
    FailureType.RE:  0.6,
    FailureType.WA:  0.4,
    FailureType.NONE: 0.0,
}

DEFAULT_COMPILE_PENALTY_PER_FAIL = 0.1
MAX_COMPILE_PENALTY = 0.3


def compute_hacker_reward(
    sandbox_verdicts: List[Dict[str, Any]],
    compile_failures: int = 0,
    per_compile_penalty: float = DEFAULT_COMPILE_PENALTY_PER_FAIL,
) -> float:
    """
    Compute the continuous Hacker reward signal.

    Args:
        sandbox_verdicts: List of SandboxVerdict dicts from evaluate_verdict().
        compile_failures: Number of Generator compilation attempts that failed.
        per_compile_penalty: Penalty deducted per compile failure.

    Returns:
        Float in [-1.0, 1.0].
    """
    # Separate verdicts by class
    valid_verdicts = [v for v in sandbox_verdicts if v["verdict"] != VerdictStatus.INVALID_INPUT]
    break_verdicts = [v for v in valid_verdicts if v["verdict"] == VerdictStatus.VALID_AND_BREAK]

    # --- valid_ratio ---
    n_total = max(1, len(sandbox_verdicts))
    n_valid = len(valid_verdicts)
    valid_ratio = n_valid / n_total

    # --- break_ratio ---
    n_valid_denom = max(1, n_valid)
    n_break = len(break_verdicts)
    break_ratio = n_break / n_valid_denom

    # --- severity_bonus (max over all breaks) ---
    severity_bonus = 0.0
    if break_verdicts:
        max_severity = max(
            SEVERITY_WEIGHTS.get(v["failure_type"], 0.0)
            for v in break_verdicts
        )
        severity_bonus = max_severity

    # --- compile_penalty (capped) ---
    compile_penalty = min(compile_failures * per_compile_penalty, MAX_COMPILE_PENALTY)

    raw = (0.2 * valid_ratio) + (0.6 * break_ratio) + (0.2 * severity_bonus) - compile_penalty
    return float(max(-1.0, min(1.0, raw)))
