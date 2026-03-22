def test_run_one_reports_hack_broken_when_hacker_finds_bug_at_terminal_state(load_repo_module, monkeypatch):
    module = load_repo_module("scripts/run_baseline.py")

    monkeypatch.setattr(
        module,
        "run_workflow",
        lambda problem, config: {
            "status": "max_iterations",
            "iteration": 1,
            "max_iterations": 1,
            "llm_calls": 7,
            "tests": {
                "pass_rate": 1.0,
                "total_tests": 3,
                "passed_tests": 2,
            },
            "hack_passed": False,
            "hack_round": 1,
            "hack_result": "BREAK",
        },
    )

    record = module.run_one({"description": "demo"}, {"max_iterations": 1})

    assert record["status"] == "max_iterations"
    assert record["hack_outcome"] == "hack_broken"


def test_run_one_reports_structured_generation_failure(load_repo_module, monkeypatch):
    module = load_repo_module("scripts/run_baseline.py")

    monkeypatch.setattr(
        module,
        "run_workflow",
        lambda problem, config: {
            "status": "success",
            "iteration": 0,
            "max_iterations": 1,
            "llm_calls": 9,
            "tests": {
                "pass_rate": 1.0,
                "total_tests": 3,
                "passed_tests": 3,
            },
            "hack_passed": True,
            "hack_round": 1,
            "hack_result": "GEN_FAILED",
            "generator_failure_kind": "validator_rejected",
            "generator_failure_reason": "Strings must be pairwise distinct",
        },
    )

    record = module.run_one({"description": "demo"}, {"max_iterations": 1})

    assert record["hack_outcome"] == "final_ac"
    assert record["gen_fail_kind"] == "validator_rejected"
    assert "pairwise distinct" in record["gen_fail_reason"]
