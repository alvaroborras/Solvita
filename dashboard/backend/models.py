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
