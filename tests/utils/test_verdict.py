from src.utils.verdict import evaluate_verdict, VerdictStatus, FailureType

def test_invalid_input():
    verdict = evaluate_verdict(validator_ok=False, exec_returncode=0, exec_timeout=False)
    assert verdict["verdict"] == VerdictStatus.INVALID_INPUT
    assert verdict["failure_type"] == FailureType.NONE

def test_valid_but_safe():
    verdict = evaluate_verdict(
        validator_ok=True, exec_returncode=0, exec_timeout=False, 
        checker_ok=True, output_matches_expected=True
    )
    assert verdict["verdict"] == VerdictStatus.VALID_BUT_SAFE
    assert verdict["failure_type"] == FailureType.NONE

def test_tle_break():
    verdict = evaluate_verdict(validator_ok=True, exec_returncode=124, exec_timeout=True)
    assert verdict["verdict"] == VerdictStatus.VALID_AND_BREAK
    assert verdict["failure_type"] == FailureType.TLE

def test_re_break():
    verdict = evaluate_verdict(validator_ok=True, exec_returncode=-11, exec_timeout=False)
    assert verdict["verdict"] == VerdictStatus.VALID_AND_BREAK
    assert verdict["failure_type"] == FailureType.RE

def test_mle_break():
    verdict = evaluate_verdict(
        validator_ok=True, exec_returncode=-9, exec_timeout=False, 
        stderr="terminating with std::bad_alloc"
    )
    assert verdict["verdict"] == VerdictStatus.VALID_AND_BREAK
    assert verdict["failure_type"] == FailureType.MLE

def test_wa_checker_break():
    verdict = evaluate_verdict(validator_ok=True, exec_returncode=0, exec_timeout=False, checker_ok=False)
    assert verdict["verdict"] == VerdictStatus.VALID_AND_BREAK
    assert verdict["failure_type"] == FailureType.WA

def test_wa_output_mismatch_break():
    verdict = evaluate_verdict(
        validator_ok=True, exec_returncode=0, exec_timeout=False, 
        checker_ok=None, output_matches_expected=False
    )
    assert verdict["verdict"] == VerdictStatus.VALID_AND_BREAK
    assert verdict["failure_type"] == FailureType.WA
