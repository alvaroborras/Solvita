"""Problem metadata helpers."""

import re
from typing import Any, Dict, Optional


def extract_problem_code(raw_problem: Dict[str, Any]) -> Optional[str]:
    """
    Extract problem code from metadata.

    Supports:
    - _metadata.problem_id: "1575_B"
    - _metadata.name: "1575_B. Building an Amusement Park"
    - _metadata.question_id: "1873_A"
    """
    metadata = raw_problem.get("_metadata", {}) if isinstance(raw_problem, dict) else {}

    for key in ("problem_id", "name", "question_id"):
        val = metadata.get(key)
        if not val or not isinstance(val, str):
            continue
        match = re.search(r"(\d+_[A-Z])", val)
        if match:
            return match.group(1)

    return None
