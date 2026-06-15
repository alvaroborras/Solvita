from __future__ import annotations

import asyncio
from fastapi import WebSocket


class WebSocketManager:
    """Manages WebSocket connections grouped by run_id."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(run_id, None)

    async def broadcast(self, run_id: str, message: dict) -> None:
        conns = self._connections.get(run_id, [])
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(run_id, ws)

    def has_subscribers(self, run_id: str) -> bool:
        return bool(self._connections.get(run_id))
