"""Global NDJSON event emitter for CLI streaming mode.

When ``configure(enabled=True)`` is called, ``emit()`` prints one JSON object
per line to stdout (flushed immediately).  Otherwise it is a no-op so the
rest of the codebase is unaffected during normal / benchmark runs.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_enabled: bool = False


def configure(enabled: bool) -> None:
    """Enable or disable event streaming.  Call once at process start."""
    global _enabled
    _enabled = enabled


def is_enabled() -> bool:
    return _enabled


def emit(event_type: str, **data: Any) -> None:
    """Emit a structured event to stdout as a single JSON line.

    Args:
        event_type: Short string identifier, e.g. ``"phase_start"``.
        **data: Arbitrary key/value payload merged into the JSON object.
    """
    if not _enabled:
        return
    payload: dict[str, Any] = {"type": event_type, **data}
    print(json.dumps(payload, ensure_ascii=False), flush=True)
