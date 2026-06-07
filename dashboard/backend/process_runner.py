from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from .config import MAIN_PY, PROJECT_ROOT, VENV_PYTHON
    from .event_store import EventStore
    from .ws_manager import WebSocketManager
except ImportError:
    from config import MAIN_PY, PROJECT_ROOT, VENV_PYTHON
    from event_store import EventStore
    from ws_manager import WebSocketManager


class SolveProcess:
    """Manages a single main.py subprocess with --stream-events."""

    def __init__(
        self,
        run_id: str,
        problem: dict[str, Any],
        config: dict[str, Any],
        manager: "ProcessManager | None" = None,
    ) -> None:
        self.run_id = run_id
        self.problem = problem
        self.config = config
        self.events: list[dict[str, Any]] = []
        self.status: str = "running"
        self.problem_id: str = "unknown"
        self.started_at: str = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self._process: asyncio.subprocess.Process | None = None
        self._seq: int = 0
        self._tmp_file: Path | None = None
        self._manager = manager
        self.completed_at: str | None = None
        self.final_status: str | None = None
        self._ws_manager: WebSocketManager | None = None
        self._event_store: EventStore | None = None
        self._finalized = False
        self._finalize_lock = asyncio.Lock()
        self._stream_task: asyncio.Task[None] | None = None
        self._cancellation_requested = False

    async def start(self, ws_manager: WebSocketManager, event_store: EventStore) -> None:
        self._ws_manager = ws_manager
        self._event_store = event_store
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="algopilot_dash_", delete=False, dir=str(PROJECT_ROOT)
        )
        tmp.write(json.dumps(self.problem, ensure_ascii=False))
        tmp.close()
        self._tmp_file = Path(tmp.name)

        python_bin = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
        cmd = [
            python_bin, str(MAIN_PY),
            "--input", str(self._tmp_file),
            "--stream-events",
        ]
        if self.config.get("max_iterations"):
            cmd += ["--max-iterations", str(self.config["max_iterations"])]

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )

        asyncio.create_task(self._drain_stderr())
        self._stream_task = asyncio.create_task(self._read_stream(ws_manager, event_store))

    async def _broadcast_best_effort(self, message: dict[str, Any]) -> None:
        if self._ws_manager is None:
            return
        try:
            await self._ws_manager.broadcast(self.run_id, message)
        except Exception:
            pass

    async def _finalize_once(self, final_status: str | None) -> bool:
        async with self._finalize_lock:
            if self._finalized:
                return False

            self.final_status = final_status
            self.status = "completed"
            self.completed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

            try:
                if self._event_store is not None:
                    self._event_store.save_run(
                        run_id=self.run_id,
                        problem_id=self.problem_id,
                        problem=self.problem,
                        config=self.config,
                        events=self.events,
                        started_at=self.started_at,
                        final_status=final_status,
                        completed_at=self.completed_at,
                    )

                self._finalized = True
                await self._broadcast_best_effort({
                    "seq": self._seq,
                    "timestamp": time.time(),
                    "event": {"type": "run_complete", "final_status": final_status},
                })
                if self._manager is not None:
                    self._manager.release(self.run_id)
                return True
            finally:
                if self._tmp_file and self._tmp_file.exists():
                    self._tmp_file.unlink()

    def _append_terminal_event(self, status: str) -> None:
        wrapped = {
            "seq": self._seq,
            "timestamp": time.time(),
            "event": {"type": "final", "status": status},
        }
        self._seq += 1
        self.events.append(wrapped)

    async def _drain_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return
        try:
            while True:
                chunk = await self._process.stderr.read(4096)
                if not chunk:
                    break
        except Exception:
            pass

    async def _read_stream(self, ws_manager: WebSocketManager, event_store: EventStore) -> None:
        self._ws_manager = ws_manager
        self._event_store = event_store
        if self._stream_task is None:
            current = asyncio.current_task()
            if current is not None:
                self._stream_task = current
        assert self._process and self._process.stdout
        buffer = b""
        try:
            while True:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    await self._handle_line(line.decode("utf-8", errors="replace"), ws_manager)
        except Exception:
            pass

        await self._process.wait()
        if buffer.strip():
            await self._handle_line(buffer.decode("utf-8", errors="replace"), ws_manager)

        final_status = None
        for e in reversed(self.events):
            ev = e.get("event", e)
            if ev.get("type") == "final":
                final_status = ev.get("status")
                break

        if self._cancellation_requested:
            return
        await self._finalize_once(final_status)

    async def _handle_line(self, line: str, ws_manager: WebSocketManager) -> None:
        if self._finalized or self._cancellation_requested:
            return
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return

        if event.get("type") == "solve_start":
            self.problem_id = event.get("problem_id", "unknown")

        wrapped = {
            "seq": self._seq,
            "timestamp": time.time(),
            "event": event,
        }
        self._seq += 1
        self.events.append(wrapped)
        await ws_manager.broadcast(self.run_id, wrapped)

    async def cancel(self) -> str:
        if self.status != "running":
            raise RuntimeError("Run is not active")

        self._cancellation_requested = True

        if self._process and self._process.returncode is None:
            self._process.terminate()
            await self._process.wait()

        if self._stream_task is not None and not self._stream_task.done():
            await self._stream_task

        has_cancelled_final = any(
            (entry.get("event", entry)).get("type") == "final"
            and (entry.get("event", entry)).get("status") == "cancelled"
            for entry in self.events
        )
        if not has_cancelled_final:
            self._append_terminal_event("cancelled")
            await self._broadcast_best_effort(self.events[-1])

        await self._finalize_once("cancelled")
        return "cancelled"


class ProcessManager:
    """Manages all active solve processes."""

    def __init__(self) -> None:
        self._processes: dict[str, SolveProcess] = {}

    def create_run(self, problem: dict[str, Any], config: dict[str, Any]) -> SolveProcess:
        run_id = uuid4().hex[:12]
        proc = SolveProcess(run_id=run_id, problem=problem, config=config, manager=self)
        self._processes[run_id] = proc
        return proc

    def get(self, run_id: str) -> SolveProcess | None:
        return self._processes.get(run_id)

    def get_buffered_events(self, run_id: str) -> list[dict[str, Any]]:
        proc = self._processes.get(run_id)
        if proc:
            return proc.events
        return []

    def release(self, run_id: str) -> None:
        self._processes.pop(run_id, None)
