import json
from pathlib import Path

from scripts.run_benchmark import _run_single_manifest, main


def test_run_single_manifest_repeat_resume_tracks_repeat_index(monkeypatch, tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    payload = tmp_path / "payload.json"
    manifest.write_text(
        json.dumps({
            "problem_id": "p1",
            "problem_payload_path": str(payload),
        }) + "\n",
        encoding="utf-8",
    )
    payload.write_text(json.dumps({"problem_id": "p1", "raw_problem": {}, "official_tests": []}), encoding="utf-8")

    class Item:
        def __init__(self, problem_id: str, problem_payload_path: str):
            self.problem_id = problem_id
            self.problem_payload_path = problem_payload_path

    monkeypatch.setattr("scripts.run_benchmark.load_benchmark_manifest", lambda path: [Item("p1", str(payload))])

    calls = []

    def fake_run_problem_modes(item, modes, config, repeat_index=1):
        calls.append((item.problem_id, tuple(modes), repeat_index))
        return [
            {
                "problem_id": item.problem_id,
                "repeat_index": repeat_index,
                "mode": mode,
                "status": "success",
                "compile_success": True,
                "passed_tests": 1,
                "total_tests": 1,
                "pass_rate": 1.0 if repeat_index == 2 else 0.0,
                "elapsed_total_s": 0.1,
                "llm_infer_s": 0.1,
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "token_usage_source": "test",
                "error": None,
                "hack_result": None,
                "hack_passed": None,
                "generator_failure_kind": None,
                "generator_failure_reason": None,
                "workflow_log_path": None,
            }
            for mode in modes
        ]

    monkeypatch.setattr("scripts.run_benchmark._run_problem_modes", fake_run_problem_modes)

    out = tmp_path / "out"
    out.mkdir()
    (out / "results.jsonl").write_text(
        json.dumps(
            {
                "problem_id": "p1",
                "repeat_index": 1,
                "mode": "solvita_pipeline",
                "status": "success",
                "compile_success": True,
                "passed_tests": 0,
                "total_tests": 1,
                "pass_rate": 0.0,
                "elapsed_total_s": 0.1,
                "llm_infer_s": 0.1,
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "token_usage_source": "test",
                "error": None,
                "hack_result": None,
                "hack_passed": None,
                "generator_failure_kind": None,
                "generator_failure_reason": None,
                "workflow_log_path": None,
            }
        ) + "\n",
        encoding="utf-8",
    )

    result = _run_single_manifest(
        manifest=manifest,
        output_dir=out,
        modes=["solvita_pipeline"],
        config_path="config/models.yaml",
        max_workers=1,
        repeat=3,
    )

    assert calls == [
        ("p1", ("solvita_pipeline",), 2),
        ("p1", ("solvita_pipeline",), 3),
    ]
    summary = result["summary"]
    assert summary["pass_at_k"]["solvita_pipeline"]["full_pass_at_k"] == 1
    assert summary["modes"]["solvita_pipeline"]["row_count"] == 3
    assert summary["modes"]["solvita_pipeline"]["problem_count"] == 1


def test_run_benchmark_writes_outputs(monkeypatch, tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("", encoding="utf-8")

    monkeypatch.setattr("scripts.run_benchmark.load_benchmark_manifest", lambda path: [])
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_benchmark.py",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(tmp_path),
        ],
    )

    main()

    assert (tmp_path / "results.jsonl").exists()
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "report.md").exists()


def test_run_benchmark_supports_bench_all(monkeypatch, tmp_path: Path):
    bench_root = tmp_path / "manifests"
    bench_root.mkdir(parents=True, exist_ok=True)

    requested_benches = []

    def _fake_build_payloads_from_hf(bench_name: str, limit, apps_difficulty=None):
        requested_benches.append((bench_name, limit))
        return [
            {
                "problem_id": f"{bench_name}_p1",
                "source": bench_name,
                "difficulty": "unknown",
                "benchmark_version": f"hf-{bench_name}",
                "raw_problem": {
                    "description": "Example problem",
                    "time_limit": 2000,
                    "space_limit": 256,
                    "public_tests": [],
                    "_metadata": {
                        "problem_id": f"{bench_name}_p1",
                        "name": "Example",
                    },
                },
                "official_tests": [{"input": "1\n", "output": "1\n"}],
                "dataset_meta": {
                    "dataset_name": f"hf/{bench_name}",
                    "split": "test",
                    "title": "Example",
                },
            }
        ]

    def _fake_load(_path: Path):
        return []

    monkeypatch.setattr("scripts.run_benchmark._build_payloads_from_hf", _fake_build_payloads_from_hf)
    monkeypatch.setattr("scripts.run_benchmark.load_benchmark_manifest", _fake_load)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_benchmark.py",
            "--bench",
            "all",
            "--bench-root",
            str(bench_root),
            "--output-dir",
            str(tmp_path / "suite_out"),
        ],
    )

    main()

    assert requested_benches == [("code-contest", None), ("apps", None), ("aethercode", None)]
    assert (tmp_path / "suite_out" / "code-contest" / "results.jsonl").exists()
    assert (tmp_path / "suite_out" / "apps" / "results.jsonl").exists()
    assert (tmp_path / "suite_out" / "aethercode" / "results.jsonl").exists()

    suite_summary = json.loads((tmp_path / "suite_out" / "suite_summary.json").read_text(encoding="utf-8"))
    assert suite_summary["bench"] == "all"
    assert len(suite_summary["runs"]) == 3


def test_run_benchmark_requires_manifest_or_bench(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_benchmark.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    try:
        main()
    except SystemExit as exc:
        assert "Either --manifest or --bench must be provided." in str(exc)
    else:
        raise AssertionError("Expected SystemExit when neither --manifest nor --bench is provided")
