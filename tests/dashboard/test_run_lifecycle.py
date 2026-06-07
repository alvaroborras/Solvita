from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from dashboard.backend import server
from dashboard.backend.event_store import EventStore
from dashboard.backend.process_runner import ProcessManager


class _BroadcastCollector:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    async def broadcast(self, run_id: str, message: dict) -> None:
        self.messages.append((run_id, message))


class _FakeStdout:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, _size: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _FakeProcess:
    def __init__(self, chunks: list[bytes]) -> None:
        self.stdout = _FakeStdout(chunks)
        self.returncode = 0

    async def wait(self) -> int:
        return 0


class _FakeCancellableProcess:
    def __init__(self, chunks: list[bytes]) -> None:
        self.stdout = _FakeStdout(chunks)
        self.returncode = None
        self.terminated = False

    async def wait(self) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15


def _configure_dashboard_runtime(monkeypatch, data_dir: Path) -> None:
    monkeypatch.setattr("dashboard.backend.event_store.DATA_DIR", data_dir, raising=False)
    server.event_store = EventStore()
    server.process_manager = ProcessManager()


def test_get_run_prefers_persisted_record_for_completed_process(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
    proc.problem_id = "demo-problem"
    proc.status = "completed"
    proc.events = [
        {"seq": 0, "timestamp": 1.0, "event": {"type": "solve_start", "problem_id": "demo-problem"}},
        {"seq": 1, "timestamp": 2.0, "event": {"type": "final", "status": "success", "iterations": 1, "pass_rate": 1.0}},
    ]

    server.event_store.save_run(
        run_id=proc.run_id,
        problem_id=proc.problem_id,
        problem=proc.problem,
        config=proc.config,
        events=proc.events,
        started_at=proc.started_at,
        final_status="success",
    )

    result = asyncio.run(server.get_run(proc.run_id))

    assert result["final_status"] == "success"
    assert result["completed_at"] is not None


def test_read_stream_persists_run_and_releases_process(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
    proc._process = _FakeProcess(
        [
            (
                b'{"type":"solve_start","problem_id":"demo-problem"}\n'
                b'{"type":"final","status":"success","iterations":1,"pass_rate":1.0}\n'
            ),
            b"",
        ]
    )
    broadcaster = _BroadcastCollector()

    asyncio.run(proc._read_stream(broadcaster, server.event_store))

    assert server.process_manager.get(proc.run_id) is None
    stored = server.event_store.get_run(proc.run_id)
    assert stored is not None
    assert stored["final_status"] == "success"
    assert any(message["event"]["type"] == "run_complete" for _, message in broadcaster.messages)


def test_cancel_run_persists_cancelled_final_event(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
    proc.problem_id = "demo-problem"
    proc._process = _FakeCancellableProcess([])
    proc._tmp_file = tmp_path / "cancel-input.json"
    proc._tmp_file.write_text("{}", encoding="utf-8")
    proc._ws_manager = _BroadcastCollector()
    proc._event_store = server.event_store

    result = asyncio.run(server.cancel_run(proc.run_id))

    assert result.run_id == proc.run_id
    assert result.cancelled is True
    assert result.final_status == "cancelled"
    assert proc._process.terminated is True

    stored = server.event_store.get_run(proc.run_id)
    assert stored is not None
    assert stored["final_status"] == "cancelled"
    assert stored["events"][-1]["event"]["type"] == "final"
    assert stored["events"][-1]["event"]["status"] == "cancelled"
    assert any(
        message["event"]["type"] == "run_complete" and message["event"]["final_status"] == "cancelled"
        for _, message in proc._ws_manager.messages
    )
    assert server.process_manager.get(proc.run_id) is None
    assert proc._tmp_file.exists() is False


def test_cancel_run_rejects_non_running_process(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Done"}}, config={})
    proc.status = "completed"
    proc.final_status = "success"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.cancel_run(proc.run_id))

    assert exc.value.status_code == 409
    assert exc.value.detail == "Run is not active"
