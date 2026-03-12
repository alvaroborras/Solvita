from enum import Enum
from typing import TypedDict, Optional

class VerdictStatus(str, Enum):
    """The overall outcome of a generated test case."""
    VALID_AND_BREAK = "VALID_AND_BREAK"     # Input was valid and broke the target
    VALID_BUT_SAFE = "VALID_BUT_SAFE"       # Input was valid but target produced correct answer
    INVALID_INPUT = "INVALID_INPUT"         # Input was rejected by validator
    ORACLE_UNCERTAIN = "ORACLE_UNCERTAIN"   # Input was valid, target errored, but no checker to verify WA vs OK (in some cases)

class FailureType(str, Enum):
    """The specific failure mode if the target broke."""
    WA = "WA"     # Wrong Answer
    RE = "RE"     # Runtime Error
    TLE = "TLE"   # Time Limit Exceeded
    MLE = "MLE"   # Memory Limit Exceeded
    NONE = "NONE" # No failure (target passed)

class SandboxVerdict(TypedDict):
    verdict: str         # VerdictStatus
    failure_type: str    # FailureType
    details: Optional[str]

def evaluate_verdict(
    validator_ok: bool,
    exec_returncode: int,
    exec_timeout: bool,
    checker_ok: Optional[bool] = None,
    output_matches_expected: Optional[bool] = None,
    stderr: str = ""
) -> SandboxVerdict:
    """
    Converts raw sandbox signals into a standardized SandboxVerdict.
    """
    if not validator_ok:
        return {
            "verdict": VerdictStatus.INVALID_INPUT.value,
            "failure_type": FailureType.NONE.value,
            "details": "Validator rejected input"
        }

    # If it reached here, input is valid.
    if exec_timeout or exec_returncode == 124:
        return {
            "verdict": VerdictStatus.VALID_AND_BREAK.value,
            "failure_type": FailureType.TLE.value,
            "details": "Time Limit Exceeded"
        }

    if exec_returncode != 0:
        # Check if stderr hints at Memory Limit (like std::bad_alloc or sigkill inside sandbox)
        # Assuming RE mostly, unless specifically identifiable as MLE
        ftype = FailureType.MLE.value if "bad_alloc" in stderr or "Memory" in stderr else FailureType.RE.value
        return {
            "verdict": VerdictStatus.VALID_AND_BREAK.value,
            "failure_type": ftype,
            "details": f"Runtime Error or Crash (Code {exec_returncode}): {stderr}"
        }

    # Executed normally. Now verify answer correctness.
    if checker_ok is False:
        return {
            "verdict": VerdictStatus.VALID_AND_BREAK.value,
            "failure_type": FailureType.WA.value,
            "details": "Wrong Answer determined by Checker"
        }
    elif output_matches_expected is False:
        return {
            "verdict": VerdictStatus.VALID_AND_BREAK.value,
            "failure_type": FailureType.WA.value,
            "details": "Wrong Answer (output mismatch)"
        }

    # All checks passed
    return {
        "verdict": VerdictStatus.VALID_BUT_SAFE.value,
        "failure_type": FailureType.NONE.value,
        "details": "Target passed successfully"
    }
