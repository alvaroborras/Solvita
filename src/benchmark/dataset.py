"""Benchmark manifest loading helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .types import BenchmarkProblem, validate_manifest_row


def load_benchmark_manifest(path: Path) -> List[BenchmarkProblem]:
    manifest_path = Path(path)
    items: List[BenchmarkProblem] = []

    with manifest_path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {lineno}: {exc}") from exc

            item = validate_manifest_row(row)
            if item.problem_payload_path.is_absolute():
                resolved_payload = item.problem_payload_path
            else:
                resolved_payload = (manifest_path.parent / item.problem_payload_path).resolve()

            if not item.has_full_tests:
                raise ValueError(
                    f"Manifest row {item.problem_id} does not satisfy has_full_tests == True"
                )
            if not resolved_payload.exists():
                raise FileNotFoundError(
                    f"Payload file does not exist for {item.problem_id}: {resolved_payload}"
                )

            items.append(
                BenchmarkProblem(
                    problem_id=item.problem_id,
                    source=item.source,
                    difficulty=item.difficulty,
                    dataset_name=item.dataset_name,
                    split=item.split,
                    has_full_tests=item.has_full_tests,
                    problem_payload_path=resolved_payload,
                    benchmark_version=item.benchmark_version,
                    time_limit=item.time_limit,
                    memory_limit=item.memory_limit,
                    tags=item.tags,
                    title=item.title,
                    language=item.language,
                    notes=item.notes,
                )
            )

    return items
