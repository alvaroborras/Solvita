from src.benchmark.modes.pipeline import run_pipeline_benchmark_case
from src.benchmark.reporting import summarize_results
from src.benchmark.types import BenchmarkResult


def test_reporting_includes_false_accept_and_verifier_rates():
    rows = [
        BenchmarkResult(
            problem_id="p1",
            mode="solvita_pipeline",
            status="success",
            compile_success=True,
            passed_tests=10,
            total_tests=10,
            elapsed_total_s=1.0,
            llm_infer_s=0.5,
            error=None,
            verifier_decision="accept",
            verifier_confidence=0.9,
            false_accept=False,
            full_testgen_completed=False,
        ),
        BenchmarkResult(
            problem_id="p2",
            mode="solvita_pipeline",
            status="success",
            compile_success=True,
            passed_tests=5,
            total_tests=10,
            elapsed_total_s=1.2,
            llm_infer_s=0.6,
            error="WA",
            verifier_decision="accept",
            verifier_confidence=0.8,
            false_accept=True,
            full_testgen_completed=True,
        ),
        BenchmarkResult(
            problem_id="p3",
            mode="solvita_pipeline",
            status="pending",
            compile_success=True,
            passed_tests=0,
            total_tests=10,
            elapsed_total_s=1.5,
            llm_infer_s=0.7,
            error=None,
            verifier_decision="repair",
            verifier_confidence=1.0,
            false_accept=False,
            full_testgen_completed=True,
        ),
        BenchmarkResult(
            problem_id="p4",
            mode="solvita_pipeline",
            status="pending",
            compile_success=True,
            passed_tests=0,
            total_tests=10,
            elapsed_total_s=1.7,
            llm_infer_s=0.8,
            error=None,
            verifier_decision="escalate_testgen",
            verifier_confidence=0.7,
            false_accept=False,
            full_testgen_completed=False,
        ),
    ]

    summary = summarize_results(rows)

    assert summary["modes"]["solvita_pipeline"]["false_accept_rate"] == 0.25
    assert summary["modes"]["solvita_pipeline"]["verifier_accept_rate"] == 0.5
    assert summary["modes"]["solvita_pipeline"]["verifier_repair_rate"] == 0.25
    assert summary["modes"]["solvita_pipeline"]["verifier_escalation_rate"] == 0.25
    assert summary["modes"]["solvita_pipeline"]["full_testgen_completion_rate"] == 0.5


def test_pipeline_mode_exposes_verification_metrics(monkeypatch):
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.run_workflow",
        lambda *a, **k: {
            "status": "success",
            "solution": {"code": "int main(){}"},
            "verification": {"decision": "accept", "confidence": 0.8},
            "tests": {"full_testgen_completed": True},
        },
    )
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.score_solution_on_official_tests",
        lambda **kwargs: {
            "compile_success": True,
            "passed_tests": 3,
            "total_tests": 4,
            "pass_rate": 0.75,
            "error": "WA",
        },
    )

    result = run_pipeline_benchmark_case(
        problem_payload={
            "problem_id": "p-metrics",
            "raw_problem": {"description": "x"},
            "official_tests": [
                {"input": "1\n", "output": "1\n"},
                {"input": "2\n", "output": "2\n"},
            ],
        }
    )

    assert result.verifier_decision == "accept"
    assert result.verifier_confidence == 0.8
    assert result.false_accept is True
    assert result.full_testgen_completed is True


def test_pipeline_mode_clears_verifier_metrics_when_best_solution_fallback_is_scored(monkeypatch):
    monkeypatch.setattr(
        "src.benchmark.modes.pipeline.run_workflow",
        lambda *a, **k: {
            "status": "max_iterations",
            "solution": {"code": "int main(){return 1;}"},
            "best_solution": {"code": "int main(){return 0;}", "passed_tests": 1},
            "verification": {"decision": "accept", "confidence": 0.9},
            "tests": {"full_testgen_completed": True},
        },
    )
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
            "problem_id": "p-fallback",
            "raw_problem": {"description": "x"},
            "official_tests": [{"input": "1\n", "output": "1\n"}],
        }
    )

    assert result.verifier_decision is None
    assert result.verifier_confidence is None
    assert result.false_accept is None
    assert result.full_testgen_completed is True


def test_reporting_excludes_unknown_verifier_metrics_from_rate_denominators():
    rows = [
        BenchmarkResult(
            problem_id="known",
            mode="solvita_pipeline",
            status="success",
            compile_success=True,
            passed_tests=10,
            total_tests=10,
            elapsed_total_s=1.0,
            llm_infer_s=0.5,
            error=None,
            verifier_decision="accept",
            verifier_confidence=0.9,
            false_accept=False,
            full_testgen_completed=True,
        ),
        BenchmarkResult(
            problem_id="fallback",
            mode="solvita_pipeline",
            status="max_iterations",
            compile_success=True,
            passed_tests=8,
            total_tests=10,
            elapsed_total_s=1.2,
            llm_infer_s=0.6,
            error=None,
            verifier_decision=None,
            verifier_confidence=None,
            false_accept=None,
            full_testgen_completed=True,
        ),
    ]

    summary = summarize_results(rows)

    assert summary["modes"]["solvita_pipeline"]["verifier_accept_rate"] == 1.0
    assert summary["modes"]["solvita_pipeline"]["verifier_repair_rate"] == 0.0
    assert summary["modes"]["solvita_pipeline"]["verifier_escalation_rate"] == 0.0
    assert summary["modes"]["solvita_pipeline"]["false_accept_rate"] == 0.0
