import json
from typing import Any, Dict, List, Tuple

from loguru import logger

from src.utils.json_utils import parse_json_response
from src.utils.patch_utils import (
    apply_search_replace_blocks,
    parse_search_replace_blocks,
)


def extract_input_validity_constraints(state: Dict[str, Any]) -> Dict[str, Any]:
    problem = state.get("problem", {})
    canonical = problem.get("canonical", {})
    if canonical:
        extracted = {
            "inputs": canonical.get("inputs", {}),
            "constraints": canonical.get("constraints", {}),
            "required_properties": canonical.get("required_properties", []),
            "edge_cases": canonical.get("edge_cases", []),
        }
        if any(extracted.values()):
            return extracted

    constraints = problem.get("constraints", {})
    description = str(problem.get("description", "") or "")
    return {
        "raw_constraints": constraints,
        "description_excerpt": description[:1500],
    }


def render_input_validity_constraints(state: Dict[str, Any]) -> str:
    return json.dumps(extract_input_validity_constraints(state), indent=2, ensure_ascii=False)


def normalize_repair_checklist(raw_checklist: Any, fallback_reason: str = "") -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {
        "must_fix": [],
        "do_not_regress": [],
        "attack_goal": [],
    }
    if isinstance(raw_checklist, dict):
        for key in normalized:
            value = raw_checklist.get(key, [])
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                normalized[key] = [str(item).strip() for item in value if str(item).strip()]

    if not normalized["must_fix"]:
        normalized["must_fix"] = [fallback_reason or "Fix the latest reported generator failure."]
    if not normalized["do_not_regress"]:
        normalized["do_not_regress"] = [
            "Keep previously satisfied input-validity constraints intact.",
        ]
    if not normalized["attack_goal"]:
        normalized["attack_goal"] = [
            "Preserve the generator's adversarial intent after validity is restored.",
        ]
    return normalized


def parse_repair_checklist(response_text: str, fallback_reason: str = "") -> Dict[str, List[str]]:
    try:
        raw = parse_json_response(response_text or "")
    except Exception as exc:
        logger.warning(f"[Generator Repair] Failed to parse checklist JSON: {exc}")
        raw = {}
    return normalize_repair_checklist(raw, fallback_reason=fallback_reason)


def render_repair_checklist(checklist: Dict[str, List[str]]) -> str:
    return json.dumps(checklist, indent=2, ensure_ascii=False)


def apply_patch_response(original_code: str, patch_response: str) -> Tuple[bool, str, str]:
    blocks = parse_search_replace_blocks(patch_response or "")
    return apply_search_replace_blocks(original_code, blocks)
