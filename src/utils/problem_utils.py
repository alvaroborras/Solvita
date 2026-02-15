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

    problem_id = None
    for key in ("problem_id", "name", "question_id"):
        val = metadata.get(key)
        if val:
            problem_id = val
            break

    if not problem_id or not isinstance(problem_id, str):
        return None

    match = re.match(r"^(\d+_[A-Z])", problem_id)
    return match.group(1) if match else None
