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
