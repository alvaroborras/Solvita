"""Helpers for collecting and estimating LLM token usage."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, Mapping

import tiktoken


TOKEN_USAGE_ACCUMULATOR_KEY = "_token_usage_accumulator"


def _default_accumulator() -> Dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "llm_calls": 0,
        "source_counts": {
            "api": 0,
            "estimated": 0,
            "mixed": 0,
        },
    }


def ensure_token_usage_accumulator(config: Dict[str, Any] | None) -> Dict[str, Any]:
    if config is None:
        raise ValueError("config must be a dict to hold token usage")
    accumulator = config.get(TOKEN_USAGE_ACCUMULATOR_KEY)
    if not isinstance(accumulator, dict):
        accumulator = _default_accumulator()
        config[TOKEN_USAGE_ACCUMULATOR_KEY] = accumulator
        return accumulator

    accumulator.setdefault("prompt_tokens", 0)
    accumulator.setdefault("completion_tokens", 0)
    accumulator.setdefault("llm_calls", 0)
    source_counts = accumulator.setdefault("source_counts", {})
    for key in ("api", "estimated", "mixed"):
        source_counts.setdefault(key, 0)
    return accumulator


def _usage_source_from_counts(source_counts: Mapping[str, Any]) -> str:
    api = int(source_counts.get("api", 0) or 0)
    estimated = int(source_counts.get("estimated", 0) or 0)
    mixed = int(source_counts.get("mixed", 0) or 0)
    nonzero = sum(1 for value in (api, estimated, mixed) if value > 0)
    if nonzero == 0:
        return "untracked"
    if nonzero == 1:
        if api > 0:
            return "api"
        if estimated > 0:
            return "estimated"
        return "mixed"
    return "mixed"


def get_token_usage_snapshot(config_or_accumulator: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(config_or_accumulator, dict):
        accumulator = _default_accumulator()
    elif TOKEN_USAGE_ACCUMULATOR_KEY in config_or_accumulator:
        accumulator = ensure_token_usage_accumulator(config_or_accumulator)
    else:
        accumulator = dict(_default_accumulator())
        accumulator.update(config_or_accumulator)
        source_counts = accumulator.setdefault("source_counts", {})
        for key in ("api", "estimated", "mixed"):
            source_counts.setdefault(key, 0)

    return {
        "prompt_tokens": int(accumulator.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(accumulator.get("completion_tokens", 0) or 0),
        "llm_calls": int(accumulator.get("llm_calls", 0) or 0),
        "token_usage_source": _usage_source_from_counts(accumulator.get("source_counts", {})),
    }


def record_token_usage(
    accumulator: Dict[str, Any],
    prompt_tokens: int,
    completion_tokens: int,
    source: str,
) -> None:
    usage_accumulator = ensure_token_usage_accumulator({TOKEN_USAGE_ACCUMULATOR_KEY: accumulator})
    usage_accumulator["prompt_tokens"] += int(prompt_tokens or 0)
    usage_accumulator["completion_tokens"] += int(completion_tokens or 0)
    usage_accumulator["llm_calls"] += 1
    source_counts = usage_accumulator.setdefault("source_counts", {})
    normalized_source = source if source in ("api", "estimated", "mixed") else "mixed"
    source_counts[normalized_source] = int(source_counts.get(normalized_source, 0) or 0) + 1


def estimate_tokens_from_chars(char_count: int) -> int:
    return max(0, int(math.ceil(max(char_count, 0) / 4.0)))


def _get_encoding(model: str | None):
    model_name = model or ""
    try:
        if model_name:
            return tiktoken.encoding_for_model(model_name)
    except Exception:
        pass
    return tiktoken.get_encoding("o200k_base")


def estimate_text_tokens(text: str, model: str | None = None) -> int:
    if not text:
        return 0
    return len(_get_encoding(model).encode(text))


def flatten_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item.get("text") or ""))
                elif item.get("type") == "text":
                    parts.append(str(item.get("content") or ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
                continue
            text_attr = getattr(item, "text", None)
            if text_attr is not None:
                parts.append(str(text_attr))
                continue
            parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, sort_keys=True)
    text_attr = getattr(content, "text", None)
    if text_attr is not None:
        return str(text_attr)
    return str(content)


def estimate_message_tokens(messages: Iterable[Mapping[str, Any]], model: str | None = None) -> int:
    total = 0
    for message in messages:
        total += 4
        total += estimate_text_tokens(str(message.get("role", "")), model=model)
        total += estimate_text_tokens(flatten_message_content(message.get("content")), model=model)
        if message.get("name"):
            total += estimate_text_tokens(str(message.get("name", "")), model=model)
    return total + 2


def _get_field(obj: Any, field: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def extract_usage_counts(response: Any) -> Dict[str, int | None]:
    usage = _get_field(response, "usage")
    prompt_tokens = _get_field(usage, "prompt_tokens")
    completion_tokens = _get_field(usage, "completion_tokens")
    return {
        "prompt_tokens": int(prompt_tokens) if prompt_tokens is not None else None,
        "completion_tokens": int(completion_tokens) if completion_tokens is not None else None,
    }


def extract_completion_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    content = _get_field(response, "content")
    if content:
        return flatten_message_content(content)
    choices = _get_field(response, "choices") or []
    if not choices:
        return ""
    first_choice = choices[0]
    message = _get_field(first_choice, "message")
    if message is not None:
        return flatten_message_content(_get_field(message, "content"))
    return flatten_message_content(_get_field(first_choice, "text"))
