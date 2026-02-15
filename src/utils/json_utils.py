"""JSON parsing utilities for LLM responses."""

import json
from loguru import logger


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks.

    Supports:
    - Pure JSON: {"key": "value"}
    - Markdown wrapped: ```json\n{"key": "value"}\n```
    - Generic code block: ```\n{"key": "value"}\n```
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

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(
                    "Response content: "
                    + cleaned[start:min(end + 1, start + 200)]
                    + "..."
                )
                raise
        logger.error("Failed to parse JSON response: no JSON object found")
        logger.debug(f"Response content: {cleaned[:200]}...")
        raise
