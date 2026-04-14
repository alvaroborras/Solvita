"""JSON parsing utilities for LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, List, Optional, Tuple

from loguru import logger


def _extract_first_balanced_object(raw: str) -> str | None:
    """
    From the first ``{``, extract a brace-balanced JSON object substring (braces inside
    strings do not affect depth). Safer than ``find('{') + rfind('}')`` when values contain ``}``.
    """
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    i = start
    n = len(raw)
    while i < n:
        c = raw[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
        i += 1
    return None


def _remove_trailing_commas(text: str) -> str:
    """Remove trailing commas before ``}`` / ``]`` (common non-standard JSON)."""
    prev = None
    out = text
    while prev != out:
        prev = out
        out = re.sub(r",(\s*})", r"\1", out)
        out = re.sub(r",(\s*])", r"\1", out)
    return out


def _preprocess_json_with_bare_newlines(raw: str) -> str:
    """
    Attempt to sanitize a JSON string where the model emitted literal newlines
    inside string values (violating the JSON spec).
    We scan character-by-character and replace bare newlines that appear
    inside a JSON string literal with their escaped counterparts.
    """
    result = []
    in_string = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and in_string:
            # Keep escape sequences intact
            result.append(ch)
            if i + 1 < len(raw):
                result.append(raw[i + 1])
                i += 2
            else:
                i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def _candidate_json_string_from_llm_response(response: str) -> str:
    """Strip markdown fences and extract a JSON object substring from an LLM reply."""
    cleaned = response.strip()

    if "```json" in cleaned:
        parts = cleaned.split("```json")
        if len(parts) > 1:
            cleaned = parts[1].split("```")[0].strip()
    elif "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1].strip()

    balanced = _extract_first_balanced_object(cleaned)
    if balanced is not None:
        return balanced
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _parse_json_candidate(candidate: str, *, log_recovery: bool) -> Any:
    attempts: List[Tuple[str, Callable[[str], Any]]] = [
        ("direct", lambda s: json.loads(s)),
        ("bare_newlines", lambda s: json.loads(_preprocess_json_with_bare_newlines(s))),
        ("trailing_commas", lambda s: json.loads(_remove_trailing_commas(s))),
        (
            "bare_newlines+trailing_commas",
            lambda s: json.loads(
                _remove_trailing_commas(_preprocess_json_with_bare_newlines(s))
            ),
        ),
    ]
    last_err: Optional[json.JSONDecodeError] = None
    for name, fn in attempts:
        try:
            result = fn(candidate)
            if log_recovery and name != "direct":
                logger.warning("parse_json_response: recovered via {}", name)
            return result
        except json.JSONDecodeError as e:
            last_err = e
            continue
    if last_err is not None:
        raise last_err
    raise json.JSONDecodeError("empty candidate", candidate, 0)


def try_parse_json_dict(response: str) -> Optional[dict]:
    """
    Best-effort parse of a JSON object from an LLM reply; returns ``None`` on failure (no logs).
    Used for multi-stage fallbacks (e.g. skill selection: JSON then substring id match).
    """
    try:
        candidate = _candidate_json_string_from_llm_response(response)
        result = _parse_json_candidate(candidate, log_recovery=False)
    except json.JSONDecodeError:
        return None
    if isinstance(result, dict):
        return result
    return None


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks.

    Supports:
    - Pure JSON: {"key": "value"}
    - Markdown wrapped: ```json\\n{"key": "value"}\\n```
    - Generic code block: ```\\n{"key": "value"}\\n```
    - Bare newlines inside string values (model non-compliance fallback)
    """
    candidate = _candidate_json_string_from_llm_response(response)
    try:
        result = _parse_json_candidate(candidate, log_recovery=True)
    except json.JSONDecodeError as last_err:
        logger.error("Failed to parse JSON response: {}", last_err)
        logger.debug("Response content: " + candidate[:200] + "...")
        raise
    if not isinstance(result, dict):
        err = json.JSONDecodeError("expected JSON object", candidate, 0)
        logger.error("Failed to parse JSON response: {}", err)
        logger.debug("Response content: " + candidate[:200] + "...")
        raise err
    return result
