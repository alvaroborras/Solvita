from src.hacker.logging import build_hacker_event_payload


def test_build_hacker_event_payload_includes_training_signals():
    payload = build_hacker_event_payload(
        route_used="stress",
        hack_result="SAFE",
        failure_type="NONE",
        generator_failure_kind="",
        compile_failures=2,
        validity_passed=True,
        buggy_distinguished=False,
        reward=0.1,
    )

    assert payload["route_used"] == "stress"
    assert payload["hack_result"] == "SAFE"
    assert payload["compile_failures"] == 2
    assert payload["reward"] == 0.1
