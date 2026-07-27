"""Stable, dependency-light contracts for heuristic runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable


class Fidelity(str, Enum):
    SEARCH = "10s"
    PROMOTION = "60s"


@runtime_checkable
class ProblemAdapter(Protocol):
    problem_id: str
    objective: str
    scorer_version: str

    def discover_instances(self) -> list[str]: ...
    def load_instance(self, instance_id: str) -> Mapping[str, Any]: ...
    def instance_stdin(self, instance_id: str) -> bytes: ...
    def parse_output(self, stdout: bytes) -> Any: ...
    def validate(self, instance_id: str, solution: Any) -> Mapping[str, Any]: ...
    def features(self, instance_id: str) -> Mapping[str, float]: ...
    def split(self) -> tuple[list[str], list[str]]: ...
    def hash(self) -> str: ...


@dataclass(frozen=True)
class ResourceLimits:
    time_limit_ms: int
    memory_mb: int = 1024
    output_bytes: int = 1_000_000
    pids: int = 64


@dataclass(frozen=True)
class ProblemManifestV1:
    problem_id: str
    version: str
    problem_family: str = ""
    objective: str = "minimize"
    adapter: str = "adapter.py"
    scorer_version: str = "1"
    instances_dir: str = "train"
    validation_instances: tuple[str, ...] = ()
    train_instances: tuple[str, ...] = ()
    allowed_standards: tuple[str, ...] = ("c++17", "c++20", "c++23")
    default_standard: str = "c++23"
    search_limits: ResourceLimits = ResourceLimits(10_000)
    final_limits: ResourceLimits = ResourceLimits(60_000)
    sdk_version: str = "1"
    baseline_bundle: str = "baseline/main.cpp"
    bks_artifacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.objective not in {"minimize", "maximize"}:
            raise ValueError("objective must be minimize or maximize")
        if self.default_standard not in self.allowed_standards:
            raise ValueError("default_standard must be one of allowed_standards")
        if not self.problem_id or Path(self.problem_id).name != self.problem_id:
            raise ValueError("problem_id must be a simple non-empty identifier")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ProblemManifestV1":
        def limits(value: Any, fallback: ResourceLimits) -> ResourceLimits:
            if not isinstance(value, Mapping):
                return fallback
            return ResourceLimits(
                int(value.get("time_limit_ms", fallback.time_limit_ms)),
                int(value.get("memory_mb", fallback.memory_mb)),
                int(value.get("output_bytes", fallback.output_bytes)),
                int(value.get("pids", fallback.pids)),
            )

        return cls(
            problem_id=str(raw["problem_id"]),
            version=str(raw.get("version", "1")),
            problem_family=str(raw.get("problem_family", raw["problem_id"])),
            objective=str(raw.get("objective", "minimize")),
            adapter=str(raw.get("adapter", "adapter.py")),
            scorer_version=str(raw.get("scorer_version", "1")),
            instances_dir=str(raw.get("instances_dir", "train")),
            train_instances=tuple(map(str, raw.get("train_instances", []))),
            validation_instances=tuple(map(str, raw.get("validation_instances", []))),
            allowed_standards=tuple(
                map(str, raw.get("allowed_standards", ["c++17", "c++20", "c++23"]))
            ),
            default_standard=str(raw.get("default_standard", "c++23")),
            search_limits=limits(raw.get("search_limits"), ResourceLimits(10_000)),
            final_limits=limits(raw.get("final_limits"), ResourceLimits(60_000)),
            sdk_version=str(raw.get("sdk_version", "1")),
            baseline_bundle=str(raw.get("baseline_bundle", "baseline/main.cpp")),
            bks_artifacts=tuple(map(str, raw.get("bks_artifacts", []))),
        )

    def digest(self) -> str:
        payload = json.dumps(
            self.__dict__, sort_keys=True, default=lambda x: x.__dict__
        ).encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class EvaluationRecord:
    candidate_hash: str
    problem_id: str
    instance_id: str
    fidelity: Fidelity
    seed: int
    scorer_version: str
    feasible: bool
    objective: float | None = None
    components: Mapping[str, float] = field(default_factory=dict)
    runtime_ms: int | None = None
    output_artifact: str | None = None
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["fidelity"] = self.fidelity.value
        result["components"] = dict(self.components)
        return result
