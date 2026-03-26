"""Utilities for keeping prompts within model context budgets."""

from __future__ import annotations

import json
from typing import Any, Iterable, List


def truncate_for_prompt(text: str, max_chars: int, label: str) -> str:
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    omitted = len(text) - max_chars
    return text[:head] + f"\n... [TRUNCATED {label} {omitted} CHARS] ...\n" + text[-tail:]


def compact_json_for_prompt(value: Any, max_chars: int, label: str) -> str:
    rendered = json.dumps(value, indent=2, ensure_ascii=False)
    return truncate_for_prompt(rendered, max_chars=max_chars, label=label)


def compact_list_for_prompt(values: Iterable[str], max_items: int, item_chars: int, label: str) -> List[str]:
    return [
        truncate_for_prompt(value, item_chars, f"{label}_{idx}")
        for idx, value in enumerate(list(values)[:max_items], 1)
    ]
