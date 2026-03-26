from pathlib import Path

import pytest

from src.benchmark.dataset import load_benchmark_manifest


def test_load_benchmark_manifest_reads_jsonl(tmp_path: Path):
    payload = tmp_path / "problem.json"
    payload.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        (
            '{"problem_id":"cc_001","source":"CodeContests","difficulty":"C",'
            '"dataset_name":"codetest","split":"benchmark","has_full_tests":true,'
            f'"problem_payload_path":"{payload.name}","benchmark_version":"v1"}}\n'
        ),
        encoding="utf-8",
    )

    items = load_benchmark_manifest(manifest)
    assert len(items) == 1
    assert items[0].problem_id == "cc_001"


def test_load_benchmark_manifest_rejects_rows_without_full_tests(tmp_path: Path):
    payload = tmp_path / "problem.json"
    payload.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        (
            '{"problem_id":"cc_001","source":"CodeContests","difficulty":"C",'
            '"dataset_name":"codetest","split":"benchmark","has_full_tests":false,'
            f'"problem_payload_path":"{payload.name}","benchmark_version":"v1"}}\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="has_full_tests"):
        load_benchmark_manifest(manifest)


def test_load_benchmark_manifest_rejects_missing_payload_file(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        (
            '{"problem_id":"cc_001","source":"CodeContests","difficulty":"C",'
            '"dataset_name":"codetest","split":"benchmark","has_full_tests":true,'
            '"problem_payload_path":"missing.json","benchmark_version":"v1"}\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="missing.json"):
        load_benchmark_manifest(manifest)


def test_load_benchmark_manifest_preserves_order(tmp_path: Path):
    payload_a = tmp_path / "a.json"
    payload_b = tmp_path / "b.json"
    payload_a.write_text("{}", encoding="utf-8")
    payload_b.write_text("{}", encoding="utf-8")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join(
            [
                (
                    '{"problem_id":"first","source":"CodeContests","difficulty":"C",'
                    '"dataset_name":"codetest","split":"benchmark","has_full_tests":true,'
                    '"problem_payload_path":"a.json","benchmark_version":"v1"}'
                ),
                (
                    '{"problem_id":"second","source":"CodeContests","difficulty":"D",'
                    '"dataset_name":"codetest","split":"benchmark","has_full_tests":true,'
                    '"problem_payload_path":"b.json","benchmark_version":"v1"}'
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    items = load_benchmark_manifest(manifest)
    assert [item.problem_id for item in items] == ["first", "second"]
