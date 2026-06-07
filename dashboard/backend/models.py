from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    problem: dict[str, Any]
    config: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    run_id: str
    status: str
    ws_url: str


class RunCancelResponse(BaseModel):
    run_id: str
    cancelled: bool
    final_status: str


class RunDeleteResponse(BaseModel):
    run_id: str
    deleted: bool


class RunSummary(BaseModel):
    run_id: str
    problem_id: str
    status: str
    final_status: str | None = None
    started_at: str
    duration_s: float | None = None
    iterations: int | None = None
    pass_rate: float | None = None


class RunDetail(BaseModel):
    run_id: str
    problem_id: str
    problem: dict[str, Any]
    config: dict[str, Any]
    started_at: str
    completed_at: str | None = None
    final_status: str | None = None
    events: list[dict[str, Any]]


class PublicTestCase(BaseModel):
    input: str = ""
    output: str = ""


class CustomProblemRequest(BaseModel):
    title: str
    description: str
    source: str = "custom"
    difficulty: str | int | None = None
    constraints_text: str = ""
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None
    public_tests: list[PublicTestCase] = Field(default_factory=list)


class CustomProblemResponse(BaseModel):
    problem_id: str
    filename: str
    problem: dict[str, Any]


class CustomProblemDeleteResponse(BaseModel):
    deleted: bool
    filename: str


class CodeforcesSearchResult(BaseModel):
    contest_id: int
    index: str
    name: str
    rating: int | None = None
    tags: list[str] = Field(default_factory=list)
    url: str
    problem_id: str


class CodeforcesSearchResponse(BaseModel):
    results: list[CodeforcesSearchResult] = Field(default_factory=list)
    cache_status: str


class CodeforcesImportRequest(BaseModel):
    contest_id: int | None = None
    index: str | None = None
    url: str | None = None

    @property
    def uses_key(self) -> bool:
        return self.contest_id is not None and bool(self.index)


class CodeforcesImportResponse(BaseModel):
    problem_id: str
    filename: str
    problem: dict[str, Any]
