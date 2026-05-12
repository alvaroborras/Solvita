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


def emit_token_sample(config_or_accumulator: Any) -> None:
    """Emit a ``token_sample`` event with current cumulative token usage.

    Reads from the project's token accumulator (``src.llm.token_usage``).
    Safe to call at any phase boundary: before the accumulator exists this is
    a no-op rather than an error.
    """
    if not _enabled:
        return
    try:
        from src.llm.token_usage import get_token_usage_snapshot  # local import to avoid cycle

        snap = get_token_usage_snapshot(config_or_accumulator) or {}
        prompt = int(snap.get("prompt_tokens", 0) or 0)
        completion = int(snap.get("completion_tokens", 0) or 0)
        emit(
            "token_sample",
            prompt_tokens=prompt,
            completion_tokens=completion,
            total=prompt + completion,
        )
    except Exception:
        # Never break the workflow because of telemetry.
        return


def _truncate(s: Any, limit: int = 200) -> str:
    """Coerce to str and truncate with an ellipsis to keep stdout readable."""
    try:
        text = str(s) if s is not None else ""
    except Exception:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"

