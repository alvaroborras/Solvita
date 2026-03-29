from src.hacker.dataset import build_hacker_candidate_record


def test_build_hacker_candidate_record_captures_route_and_failure():
    record = build_hacker_candidate_record(
        problem_id="p1",
        route_used="semantic",
        hack_result="BREAK",
        failure_type="WA",
        generator_failure_kind="",
        reward=0.88,
        validity_passed=True,
        buggy_distinguished=True,
        compile_failures=0,
    )

    assert record["problem_id"] == "p1"
    assert record["route_used"] == "semantic"
    assert record["hack_result"] == "BREAK"
    assert record["failure_type"] == "WA"
    assert record["reward"] == 0.88
