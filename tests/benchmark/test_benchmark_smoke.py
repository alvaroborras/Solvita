import json
from pathlib import Path

from scripts.run_benchmark import main
from src.benchmark.types import BenchmarkProblem, BenchmarkResult


def _write_payload(tmp_path: Path, problem_id: str) -> Path:
    payload = tmp_path / f"{problem_id}.json"
    payload.write_text(
        json.dumps(
            {
                "problem_id": problem_id,
                "raw_problem": {
                    "description": "Example problem",
                    "time_limit": 2000,
                    "space_limit": 256,
                    "public_tests": [{"input": "1\n", "output": "2\n"}],
                },
                "official_tests": [{"input": "3\n", "output": "4\n"}],
                "dataset_meta": {
                    "dataset_name": "deepmind/code_contests",
                    "split": "test",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return payload


def test_benchmark_smoke_single_pass_mode(monkeypatch, tmp_path: Path):
    payload_path = _write_payload(tmp_path, "p1")
    item = BenchmarkProblem(
        problem_id="p1",
        source="CODEFORCES",
        difficulty="C",
        dataset_name="deepmind/code_contests",
        split="test",
        has_full_tests=True,
        problem_payload_path=payload_path,
        benchmark_version="pilot-v1",
    )

    monkeypatch.setattr("scripts.run_benchmark.load_benchmark_manifest", lambda path: [item])
    monkeypatch.setitem(
        __import__("scripts.run_benchmark", fromlist=["MODE_RUNNERS"]).MODE_RUNNERS,
        "single_pass",
        lambda problem_payload, config: BenchmarkResult(
            problem_id=problem_payload["problem_id"],
            mode="single_pass",
            status="success",
            compile_success=True,
            passed_tests=1,
            total_tests=1,
            elapsed_total_s=0.2,
            llm_infer_s=0.1,
            error=None,
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_benchmark.py",
            "--manifest",
            str(tmp_path / "manifest.jsonl"),
            "--output-dir",
            str(tmp_path / "out_gpt"),
            "--modes",
            "single_pass",
        ],
    )

    main()

    results_path = tmp_path / "out_gpt" / "results.jsonl"
    row = json.loads(results_path.read_text(encoding="utf-8").strip())
    assert row["mode"] == "single_pass"
    assert row["passed_tests"] == 1
    assert row["total_tests"] == 1
    assert row["pass_rate"] == 1.0
    assert (tmp_path / "out_gpt" / "summary.json").exists()
    assert (tmp_path / "out_gpt" / "report.md").exists()


def test_benchmark_smoke_solvita_pipeline_mode(monkeypatch, tmp_path: Path):
    payload_path = _write_payload(tmp_path, "p2")
    item = BenchmarkProblem(
        problem_id="p2",
        source="CODEFORCES",
        difficulty="D",
        dataset_name="deepmind/code_contests",
        split="test",
        has_full_tests=True,
        problem_payload_path=payload_path,
        benchmark_version="pilot-v1",
    )

    monkeypatch.setattr("scripts.run_benchmark.load_benchmark_manifest", lambda path: [item])
    monkeypatch.setitem(
        __import__("scripts.run_benchmark", fromlist=["MODE_RUNNERS"]).MODE_RUNNERS,
        "solvita_pipeline",
        lambda problem_payload, config: BenchmarkResult(
            problem_id=problem_payload["problem_id"],
            mode="solvita_pipeline",
            status="success",
            compile_success=True,
            passed_tests=0,
            total_tests=1,
            elapsed_total_s=0.5,
            llm_infer_s=0.3,
            error=None,
            hack_result="SAFE",
            hack_passed=True,
            generator_failure_kind=None,
            generator_failure_reason=None,
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_benchmark.py",
            "--manifest",
            str(tmp_path / "manifest.jsonl"),
            "--output-dir",
            str(tmp_path / "out_pipeline"),
            "--modes",
            "solvita_pipeline",
        ],
    )

    main()

    results_path = tmp_path / "out_pipeline" / "results.jsonl"
    row = json.loads(results_path.read_text(encoding="utf-8").strip())
    assert row["mode"] == "solvita_pipeline"
    assert row["passed_tests"] == 0
    assert row["total_tests"] == 1
    assert row["hack_result"] == "SAFE"
    assert row["compile_success"] is True
