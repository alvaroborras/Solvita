#!/usr/bin/env python3
"""Build a small normalized benchmark pilot from deepmind/code_contests."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasets import load_dataset, load_dataset_builder


DEFAULT_BENCHMARK_ROOT = Path("/Data/lih/solvita-benchmark")
DEFAULT_DATASET = "deepmind/code_contests"
LETTER_DIFFICULTIES = [chr(code) for code in range(ord("A"), ord("V") + 1)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a normalized benchmark pilot manifest from deepmind/code_contests."
    )
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    parser.add_argument("--dataset", type=str, default=DEFAULT_DATASET)
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--source", type=str, default="CODEFORCES")
    parser.add_argument("--min-difficulty", type=str, default="C")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--benchmark-version", type=str, default="pilot-v1")
    return parser.parse_args()


def configure_hf_cache(benchmark_root: Path) -> None:
    hf_root = benchmark_root / "hf_cache"
    os.environ.setdefault("HF_HOME", str(hf_root))
    os.environ.setdefault("HF_HUB_CACHE", str(hf_root / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(hf_root / "datasets"))


def normalize_tests(test_group: Dict[str, List[str]]) -> List[Dict[str, str]]:
    inputs = list((test_group or {}).get("input", []) or [])
    outputs = list((test_group or {}).get("output", []) or [])
    return [
        {"input": inp, "output": out}
        for inp, out in zip(inputs, outputs)
    ]


def difficulty_allowed(label: str, min_label: str) -> bool:
    if label not in LETTER_DIFFICULTIES or min_label not in LETTER_DIFFICULTIES:
        return False
    return LETTER_DIFFICULTIES.index(label) >= LETTER_DIFFICULTIES.index(min_label)


def build_problem_id(row: Dict[str, Any]) -> str:
    contest_id = row.get("cf_contest_id")
    index = row.get("cf_index")
    if contest_id and index:
        return f"{contest_id}_{index}"

    name = str(row.get("name") or "unknown")
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)
    return safe.strip("_") or "unknown"


def to_time_limit_ms(time_limit: Dict[str, Any]) -> int | None:
    if not isinstance(time_limit, dict):
        return None
    seconds = time_limit.get("seconds")
    nanos = time_limit.get("nanos", 0)
    if seconds is None:
        return None
    return int(seconds) * 1000 + int(nanos or 0) // 1_000_000


def to_memory_limit_mb(memory_limit_bytes: Any) -> int | None:
    if memory_limit_bytes in (None, ""):
        return None
    return int(memory_limit_bytes) // (1024 * 1024)


def build_payload(
    row: Dict[str, Any],
    source_label: str,
    difficulty_label: str,
    benchmark_version: str,
    dataset_name: str,
    split: str,
) -> Dict[str, Any]:
    problem_id = build_problem_id(row)
    public_tests = normalize_tests(row.get("public_tests", {}))
    private_tests = normalize_tests(row.get("private_tests", {}))
    generated_tests = normalize_tests(row.get("generated_tests", {}))
    official_tests = private_tests + generated_tests

    raw_problem = {
        "description": row.get("description", ""),
        "time_limit": to_time_limit_ms(row.get("time_limit")),
        "space_limit": to_memory_limit_mb(row.get("memory_limit_bytes")),
        "public_tests": public_tests,
        "_metadata": {
            "problem_id": problem_id,
            "name": row.get("name", ""),
            "source": source_label,
            "difficulty": difficulty_label,
            "cf_rating": row.get("cf_rating"),
            "cf_contest_id": row.get("cf_contest_id"),
            "cf_index": row.get("cf_index"),
            "benchmark_version": benchmark_version,
        },
    }

    return {
        "problem_id": problem_id,
        "source": source_label,
        "difficulty": difficulty_label,
        "benchmark_version": benchmark_version,
        "raw_problem": raw_problem,
        "official_tests": official_tests,
        "dataset_meta": {
            "dataset_name": dataset_name,
            "split": split,
            "title": row.get("name", ""),
            "cf_rating": row.get("cf_rating"),
            "cf_tags": row.get("cf_tags", []),
            "input_file": row.get("input_file", ""),
            "output_file": row.get("output_file", ""),
            "public_tests_count": len(public_tests),
            "private_tests_count": len(private_tests),
            "generated_tests_count": len(generated_tests),
        },
    }


def select_rows(
    dataset_name: str,
    split: str,
    source_label: str,
    min_difficulty: str,
    limit: int,
    benchmark_version: str,
) -> List[Dict[str, Any]]:
    builder = load_dataset_builder(dataset_name)
    source_feature = builder.info.features["source"]
    difficulty_feature = builder.info.features["difficulty"]

    selected: List[Dict[str, Any]] = []
    rows = load_dataset(dataset_name, split=split, streaming=True)
    for row in rows:
        current_source = source_feature.int2str(row["source"])
        current_difficulty = difficulty_feature.int2str(row["difficulty"])
        if current_source != source_label:
            continue
        if not difficulty_allowed(current_difficulty, min_difficulty):
            continue
        payload = build_payload(
            row,
            source_label=current_source,
            difficulty_label=current_difficulty,
            benchmark_version=benchmark_version,
            dataset_name=dataset_name,
            split=split,
        )
        if not payload["official_tests"]:
            continue
        selected.append(payload)
        if len(selected) >= limit:
            break
    return selected


def write_outputs(
    benchmark_root: Path,
    payloads: Iterable[Dict[str, Any]],
    split: str,
    source_label: str,
    min_difficulty: str,
    benchmark_version: str,
) -> Dict[str, Any]:
    payload_dir = benchmark_root / "normalized" / "payloads" / benchmark_version
    manifest_dir = benchmark_root / "normalized" / "manifests"
    payload_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"{split}_{source_label.lower()}_ge_{min_difficulty.lower()}"
    manifest_path = manifest_dir / f"{benchmark_version}_{suffix}.jsonl"

    manifest_rows: List[Dict[str, Any]] = []
    with manifest_path.open("w", encoding="utf-8") as fh:
        for payload in payloads:
            payload_path = payload_dir / f"{payload['problem_id']}.json"
            payload_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            row = {
                "problem_id": payload["problem_id"],
                "source": payload["source"],
                "difficulty": payload["difficulty"],
                "dataset_name": payload["dataset_meta"]["dataset_name"],
                "split": payload["dataset_meta"]["split"],
                "has_full_tests": True,
                "problem_payload_path": str(payload_path),
                "benchmark_version": payload["benchmark_version"],
                "time_limit": payload["raw_problem"]["time_limit"],
                "memory_limit": payload["raw_problem"]["space_limit"],
                "tags": payload["dataset_meta"]["cf_tags"],
                "title": payload["dataset_meta"]["title"],
                "language": "cpp",
                "notes": {
                    "public_tests_count": payload["dataset_meta"]["public_tests_count"],
                    "private_tests_count": payload["dataset_meta"]["private_tests_count"],
                    "generated_tests_count": payload["dataset_meta"]["generated_tests_count"],
                },
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            manifest_rows.append(row)

    summary = {
        "manifest_path": str(manifest_path),
        "payload_dir": str(payload_dir),
        "count": len(manifest_rows),
        "problem_ids": [row["problem_id"] for row in manifest_rows],
    }
    summary_path = manifest_dir / f"{benchmark_version}_{suffix}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    args = parse_args()
    configure_hf_cache(args.benchmark_root)
    selected_payloads = select_rows(
        dataset_name=args.dataset,
        split=args.split,
        source_label=args.source,
        min_difficulty=args.min_difficulty,
        limit=args.limit,
        benchmark_version=args.benchmark_version,
    )
    result = write_outputs(
        benchmark_root=args.benchmark_root,
        payloads=selected_payloads,
        split=args.split,
        source_label=args.source,
        min_difficulty=args.min_difficulty,
        benchmark_version=args.benchmark_version,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
