"""Load YAML prompt templates and render with placeholder replacement."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_DEFAULT_PATH = CONFIG_DIR / "prompt_template.yaml"

_cache: Optional[Dict[str, Any]] = None
_cache_path: Optional[Path] = None


def load_prompt_templates(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load prompt templates from YAML. Raises FileNotFoundError if missing."""
    global _cache, _cache_path
    p = path or _DEFAULT_PATH
    if _cache is not None and _cache_path == p:
        return _cache
    if not p.is_file():
        raise FileNotFoundError(f"Prompt template file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        _cache = yaml.safe_load(f) or {}
    _cache_path = p
    return _cache


def clear_prompt_template_cache() -> None:
    """Clear in-process cache (for tests)."""
    global _cache, _cache_path
    _cache = None
    _cache_path = None


def get_nested_template(root: Dict[str, Any], key: str) -> Any:
    """
    Resolve dotted key, e.g. 'abstract_problem.system'.
    Raises KeyError if any segment is missing.
    """
    cur: Any = root
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(key)
        cur = cur[part]
    return cur


def render_placeholders(template: str, mapping: Dict[str, str]) -> str:
    """
    Replace <KEY> placeholders (uppercase keys in mapping).
    Example: mapping {'PROBLEM_DESC': '...'} replaces <PROBLEM_DESC>.
    """
    out = template
    for k, v in mapping.items():
        out = out.replace(f"<{k}>", str(v))
    return out
