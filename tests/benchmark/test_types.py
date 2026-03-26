import pytest

from src.benchmark.types import BenchmarkResult, validate_manifest_row


def test_validate_manifest_row_accepts_required_fields():
    row = {
        "problem_id": "cc_001",
        "source": "CodeContests",
        "difficulty": "C",
        "dataset_name": "codetest",
        "split": "benchmark",
        "has_full_tests": True,
        "problem_payload_path": "data/bench/cc_001.json",
        "benchmark_version": "v1",
    }

    item = validate_manifest_row(row)
    assert item.problem_id == "cc_001"


def test_validate_manifest_row_rejects_missing_problem_id():
    row = {
        "source": "CodeContests",
        "difficulty": "C",
        "dataset_name": "codetest",
        "split": "benchmark",
        "has_full_tests": True,
        "problem_payload_path": "data/bench/cc_001.json",
        "benchmark_version": "v1",
    }

    with pytest.raises(ValueError, match="problem_id"):
        validate_manifest_row(row)


def test_benchmark_result_computes_pass_rate():
    result = BenchmarkResult(
        problem_id="cc_001",
        mode="gpt52_single_pass",
        status="success",
        compile_success=True,
        passed_tests=8,
        total_tests=10,
        elapsed_total_s=1.2,
        llm_infer_s=0.7,
        error=None,
    )

    assert result.pass_rate == 0.8


def test_benchmark_result_rejects_negative_test_counts():
    with pytest.raises(ValueError, match="non-negative"):
        BenchmarkResult(
            problem_id="cc_001",
            mode="gpt52_single_pass",
            status="error",
            compile_success=False,
            passed_tests=-1,
            total_tests=10,
            elapsed_total_s=1.2,
            llm_infer_s=0.7,
            error="boom",
        )
