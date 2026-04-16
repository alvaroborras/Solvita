from pathlib import Path

from loguru import logger

from src.benchmark.modes.pipeline import (
    build_pipeline_benchmark_config,
    run_pipeline_benchmark_case,
)


def test_build_pipeline_benchmark_config_passes_through_network_config():
    cfg = build_pipeline_benchmark_config(
        {"max_iterations": 3, "trainable_memory": {"enabled": True, "data_dir": "x"}}
    )

    assert cfg["trainable_memory"]["enabled"] is True
    assert cfg["trainable_memory"]["data_dir"] == "x"


def test_pipeline_mode_scores_against_official_tests_not_internal_state(monkeypatch):
    captured = {}

    def fake_run_workflow(problem, config):
        captured["problem"] = problem
        captured["config"] = config
        return {
            "status": "success",
            "tests": {"passed_tests": 999, "total_tests": 999, "pass_rate": 1.0},
            "solution": {"code": "int main(){}"},
            "hack_result": "SAFE",
            "hack_passed": True,
            "prompt_tokens": 210,
            "completion_tokens": 84,
            "token_usage_source": "api",
        }

    monkeypatch.setattr("src.benchmark.modes.pipeline.run_workflow", fake_run_workflow)
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.score_solution_on_official_tests",
        lambda **kwargs: {
            "compile_success": True,
            "passed_tests": 7,
            "total_tests": 10,
            "pass_rate": 0.7,
            "error": None,
        },
    )

    result = run_pipeline_benchmark_case(
        problem_payload={
            "problem_id": "p1",
            "raw_problem": {"description": "x"},
            "official_tests": [{"input": "", "output": ""}],
        },
        config={"trainable_memory": {"enabled": True}},
    )

    assert captured["problem"] == {"description": "x"}
    assert captured["config"]["trainable_memory"]["enabled"] is True
    assert result.passed_tests == 7
    assert result.total_tests == 10
    assert result.pass_rate == 0.7
    assert result.hack_result == "SAFE"
    assert result.prompt_tokens == 210
    assert result.completion_tokens == 84
    assert result.token_usage_source == "api"


def test_pipeline_mode_preserves_generator_diagnostics(monkeypatch):
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.run_workflow",
        lambda *a, **k: {
            "status": "max_iterations",
            "solution": {"code": "int main(){}"},
            "generator_failure_kind": "validator_reject",
            "generator_failure_reason": "n exceeded max",
            "hack_result": "GEN_FAILED",
            "hack_passed": False,
        },
    )
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.score_solution_on_official_tests",
        lambda **kwargs: {
            "compile_success": False,
            "passed_tests": 0,
            "total_tests": 3,
            "pass_rate": 0.0,
            "error": "compile failed",
        },
    )

    result = run_pipeline_benchmark_case(
        problem_payload={
            "problem_id": "p2",
            "raw_problem": {"description": "x"},
            "official_tests": [{"input": "", "output": ""}],
        }
    )

    assert result.generator_failure_kind == "validator_reject"
    assert result.generator_failure_reason == "n exceeded max"
    assert result.hack_result == "GEN_FAILED"
    assert result.error == "compile failed"


def test_pipeline_mode_handles_workflow_exception(monkeypatch):
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.run_workflow",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = run_pipeline_benchmark_case(
        problem_payload={
            "problem_id": "p3",
            "raw_problem": {"description": "x"},
            "official_tests": [{"input": "", "output": ""}],
        }
    )

    assert result.status == "error"
    assert result.compile_success is False
    assert result.error == "boom"


def test_pipeline_mode_writes_per_problem_workflow_log(monkeypatch, tmp_path: Path):
    def fake_run_workflow(problem, config):
        logger.info("benchmark log line for {}", problem.get("description"))
        return {
            "status": "success",
            "tests": {"passed_tests": 1, "total_tests": 1, "pass_rate": 1.0},
            "solution": {"code": "int main(){}"},
            "hack_result": "SAFE",
            "hack_passed": True,
        }

    monkeypatch.setattr("src.benchmark.modes.pipeline.run_workflow", fake_run_workflow)
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.score_solution_on_official_tests",
        lambda **kwargs: {
            "compile_success": True,
            "passed_tests": 1,
            "total_tests": 1,
            "pass_rate": 1.0,
            "error": None,
        },
    )

    result = run_pipeline_benchmark_case(
        problem_payload={
            "problem_id": "1575_C",
            "raw_problem": {"description": "cyclic sum"},
            "official_tests": [{"input": "1\n", "output": "1\n"}],
        },
        config={"benchmark_output_dir": str(tmp_path)},
    )

    assert result.workflow_log_path is not None
    log_path = Path(result.workflow_log_path)
    assert log_path.exists()
    assert "benchmark log line for cyclic sum" in log_path.read_text(encoding="utf-8")
