import json
from pathlib import Path

from scripts.run_benchmark import main


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

    def _fake_build_payloads_from_hf(bench_name: str, limit):
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
