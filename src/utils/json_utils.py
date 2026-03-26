"""JSON parsing utilities for LLM responses."""

import json
from loguru import logger


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
        if ch == '\\' and in_string:
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
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            result.append('\\r')
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks.

    Supports:
    - Pure JSON: {"key": "value"}
    - Markdown wrapped: ```json\\n{"key": "value"}\\n```
    - Generic code block: ```\\n{"key": "value"}\\n```
    - Bare newlines inside string values (model non-compliance fallback)
    """
    cleaned = response.strip()

    if "```json" in cleaned:
        parts = cleaned.split("```json")
        if len(parts) > 1:
            cleaned = parts[1].split("```")[0].strip()
    elif "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1].strip()

    # Extract the outermost JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end + 1]
    else:
        candidate = cleaned

    # First attempt: standard parse
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Second attempt: preprocess bare newlines inside strings
    try:
        sanitized = _preprocess_json_with_bare_newlines(candidate)
        result = json.loads(sanitized)
        logger.warning("parse_json_response: recovered via bare-newline sanitization")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(
            "Response content: "
            + candidate[:200]
            + "..."
        )
        raise
