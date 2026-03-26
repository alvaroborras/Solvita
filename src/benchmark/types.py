"""Core benchmark manifest and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


REQUIRED_MANIFEST_FIELDS = (
    "problem_id",
    "source",
    "difficulty",
    "dataset_name",
    "split",
    "has_full_tests",
    "problem_payload_path",
    "benchmark_version",
)


def compute_pass_rate(passed_tests: int, total_tests: int) -> float:
    if passed_tests < 0 or total_tests < 0:
        raise ValueError("Test counts must be non-negative")
    if passed_tests > total_tests:
        raise ValueError("passed_tests cannot exceed total_tests")
    return (passed_tests / total_tests) if total_tests else 0.0


@dataclass(frozen=True)
class BenchmarkProblem:
    problem_id: str
    source: str
    difficulty: str
    dataset_name: str
    split: str
    has_full_tests: bool
    problem_payload_path: Path
    benchmark_version: str
    time_limit: Optional[int] = None
    memory_limit: Optional[int] = None
    tags: list[str] = field(default_factory=list)
    title: Optional[str] = None
    language: Optional[str] = None
    notes: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class BenchmarkResult:
    problem_id: str
    mode: str
    status: str
    compile_success: bool
    passed_tests: int
    total_tests: int
    elapsed_total_s: float
    llm_infer_s: float
    error: Optional[str]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    token_usage_source: Optional[str] = None
    hack_result: Optional[str] = None
    hack_passed: Optional[bool] = None
    generator_failure_kind: Optional[str] = None
    generator_failure_reason: Optional[str] = None
    workflow_log_path: Optional[str] = None

    def __post_init__(self) -> None:
        compute_pass_rate(self.passed_tests, self.total_tests)

    @property
    def pass_rate(self) -> float:
        return compute_pass_rate(self.passed_tests, self.total_tests)


def validate_manifest_row(row: Dict[str, Any]) -> BenchmarkProblem:
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in row]
    if missing:
        raise ValueError(f"Missing required manifest fields: {', '.join(missing)}")

    payload_path = Path(row["problem_payload_path"])

    return BenchmarkProblem(
        problem_id=str(row["problem_id"]),
        source=str(row["source"]),
        difficulty=str(row["difficulty"]),
        dataset_name=str(row["dataset_name"]),
        split=str(row["split"]),
        has_full_tests=bool(row["has_full_tests"]),
        problem_payload_path=payload_path,
        benchmark_version=str(row["benchmark_version"]),
        time_limit=row.get("time_limit"),
        memory_limit=row.get("memory_limit"),
        tags=list(row.get("tags", [])),
        title=row.get("title"),
        language=row.get("language"),
        notes=row.get("notes"),
    )
