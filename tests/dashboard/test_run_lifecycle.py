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


class _FailingBroadcastCollector:
    async def broadcast(self, run_id: str, message: dict) -> None:
        raise RuntimeError("broadcast failed")


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


class _PausingStdout:
    def __init__(self, chunks: list[bytes], pause_before_read: int, release_event: asyncio.Event) -> None:
        self._chunks = list(chunks)
        self._pause_before_read = pause_before_read
        self._release_event = release_event
        self.paused = asyncio.Event()
        self._reads = 0

    async def read(self, _size: int) -> bytes:
        if self._reads == self._pause_before_read:
            self.paused.set()
            await self._release_event.wait()
        self._reads += 1
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _FailingEventStore:
    def get_run(self, _run_id: str):
        return None

    def save_run(self, **_kwargs) -> None:
        raise RuntimeError("save failed")


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


def test_cancel_run_waits_for_stream_drain_before_finalizing(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    async def scenario() -> tuple[str, list[dict], dict | None]:
        proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
        proc.problem_id = "demo-problem"
        proc._tmp_file = tmp_path / "cancel-race-input.json"
        proc._tmp_file.write_text("{}", encoding="utf-8")
        broadcaster = _BroadcastCollector()
        release_event = asyncio.Event()
        pausing_stdout = _PausingStdout(
            [
                b'{"type":"solve_start","problem_id":"demo-problem"}\n',
                b'{"type":"progress","step":"buffered"}\n',
                b"",
            ],
            pause_before_read=1,
            release_event=release_event,
        )
        proc._process = _FakeCancellableProcess([])
        proc._process.stdout = pausing_stdout
        proc._ws_manager = broadcaster
        proc._event_store = server.event_store

        stream_task = asyncio.create_task(proc._read_stream(broadcaster, server.event_store))
        proc._stream_task = stream_task

        await pausing_stdout.paused.wait()
        cancel_task = asyncio.create_task(proc.cancel())
        await asyncio.sleep(0)
        release_event.set()

        final_status = await cancel_task
        await stream_task
        stored = server.event_store.get_run(proc.run_id)
        return final_status, [message for _, message in broadcaster.messages], stored

    final_status, messages, stored = asyncio.run(scenario())

    assert final_status == "cancelled"
    run_complete_indexes = [idx for idx, message in enumerate(messages) if message["event"]["type"] == "run_complete"]
    assert run_complete_indexes == [len(messages) - 1]
    assert stored is not None
    assert stored["final_status"] == "cancelled"
    assert stored["events"][-1]["event"]["type"] == "final"
    assert stored["events"][-1]["event"]["status"] == "cancelled"


def test_cancel_run_wins_over_buffered_natural_final(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    async def scenario():
        proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
        proc.problem_id = "demo-problem"
        proc._tmp_file = tmp_path / "cancel-natural-finish.json"
        proc._tmp_file.write_text("{}", encoding="utf-8")
        broadcaster = _BroadcastCollector()
        release_event = asyncio.Event()
        pausing_stdout = _PausingStdout(
            [
                b'{"type":"solve_start","problem_id":"demo-problem"}\n',
                b'{"type":"final","status":"success","iterations":1,"pass_rate":1.0}\n',
                b"",
            ],
            pause_before_read=1,
            release_event=release_event,
        )
        proc._process = _FakeCancellableProcess([])
        proc._process.stdout = pausing_stdout
        proc._ws_manager = broadcaster
        proc._event_store = server.event_store

        stream_task = asyncio.create_task(proc._read_stream(broadcaster, server.event_store))
        proc._stream_task = stream_task

        await pausing_stdout.paused.wait()
        cancel_task = asyncio.create_task(server.cancel_run(proc.run_id))
        await asyncio.sleep(0)
        release_event.set()

        result = await cancel_task
        await stream_task
        stored = server.event_store.get_run(proc.run_id)
        return proc, result, stored, [message for _, message in broadcaster.messages]

    proc, result, stored, messages = asyncio.run(scenario())

    assert result.run_id == proc.run_id
    assert result.final_status == "cancelled"
    assert result.cancelled is True
    assert stored is not None
    assert stored["final_status"] == "cancelled"
    assert stored["events"][-1]["event"]["type"] == "final"
    assert stored["events"][-1]["event"]["status"] == "cancelled"
    run_complete_indexes = [idx for idx, message in enumerate(messages) if message["event"]["type"] == "run_complete"]
    assert run_complete_indexes == [len(messages) - 1]


def test_cancel_run_translates_runtime_race_to_conflict(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Race"}}, config={})

    async def _raise_runtime_error() -> str:
        raise RuntimeError("Run is not active")

    monkeypatch.setattr(proc, "cancel", _raise_runtime_error)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.cancel_run(proc.run_id))

    assert exc.value.status_code == 409
    assert exc.value.detail == "Run is not active"


def test_cancel_run_cleans_up_when_persist_fails(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
    proc.problem_id = "demo-problem"
    proc._process = _FakeCancellableProcess([])
    proc._tmp_file = tmp_path / "cancel-fail-input.json"
    proc._tmp_file.write_text("{}", encoding="utf-8")
    proc._ws_manager = _BroadcastCollector()
    proc._event_store = _FailingEventStore()

    with pytest.raises(RuntimeError, match="save failed"):
        asyncio.run(proc.cancel())

    retained = server.process_manager.get(proc.run_id)
    assert retained is proc
    assert proc.status == "completed"
    assert proc.final_status == "cancelled"
    assert proc.completed_at is not None
    assert proc._tmp_file.exists() is False


def test_delete_run_rejects_active_process(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Live"}}, config={})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.delete_run(proc.run_id))

    assert exc.value.status_code == 409
    assert exc.value.detail == "Cannot delete a running run"


def test_delete_run_rejects_missing_persisted_run(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.delete_run("missing-run"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Run not found"


def test_delete_run_removes_file_and_index_entry(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    run_id = "done-run"
    server.event_store.save_run(
        run_id=run_id,
        problem_id="demo-problem",
        problem={"_metadata": {"name": "Demo"}},
        config={},
        events=[
            {"seq": 0, "timestamp": 1.0, "event": {"type": "solve_start", "problem_id": "demo-problem"}},
            {"seq": 1, "timestamp": 2.0, "event": {"type": "final", "status": "success", "iterations": 1, "pass_rate": 1.0}},
        ],
        started_at="2026-06-07T00:00:00Z",
        final_status="success",
        completed_at="2026-06-07T00:00:02Z",
    )

    result = asyncio.run(server.delete_run(run_id))

    assert result.run_id == run_id
    assert result.deleted is True
    assert server.event_store.get_run(run_id) is None
    assert all(entry["run_id"] != run_id for entry in server.event_store.list_runs())


def test_delete_run_evicts_completed_in_memory_process(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
    proc.problem_id = "demo-problem"
    proc.status = "completed"
    proc.final_status = "success"
    proc.completed_at = "2026-06-07T00:00:02Z"
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
        completed_at=proc.completed_at,
    )

    result = asyncio.run(server.delete_run(proc.run_id))

    assert result.run_id == proc.run_id
    assert result.deleted is True
    assert server.process_manager.get(proc.run_id) is None
    assert server.event_store.get_run(proc.run_id) is None
    assert all(entry["run_id"] != proc.run_id for entry in server.event_store.list_runs())
    assert asyncio.run(server.get_run(proc.run_id)) == {"error": "Run not found"}
