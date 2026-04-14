"""LLM calls to extract ``logic_analysis`` / ``logic_contrast`` JSON for graph evolution.

Templates live under ``skill_graph_train/prompt_template/`` (same as ``logic_pipeline_runner.py``).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

from skill_graph_train.bootstrap import ensure_import_paths

ensure_import_paths()

from src.llm import UnifiedLLMClient  # noqa: E402
from skill_graph_train.prompt_template_dir import LOGIC_CHAIN_TEMPLATE, LOGIC_DIFF_TEMPLATE  # noqa: E402

logger = logging.getLogger(__name__)

_TEMPLATE_CHAIN = LOGIC_CHAIN_TEMPLATE
_TEMPLATE_DIFF = LOGIC_DIFF_TEMPLATE

_MAX_CODE_CHARS = 14000


def _load_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _truncate(s: str, n: int) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    return s[:n] + "\n... [truncated]"


def _render(template: str, mapping: Dict[str, str]) -> str:
    out = template
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse first JSON object from model output (tolerates ``` fences)."""
    if not text or not text.strip():
        return None
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = t[start : end + 1]
    try:
        val = json.loads(blob)
    except json.JSONDecodeError as e:
        logger.warning("evolution_llm: JSON decode failed: %s", e)
        return None
    return val if isinstance(val, dict) else None


def run_logic_chain(
    config: Dict[str, Any],
    *,
    description: str,
    tags_csv: str,
    correct_code: str,
) -> Optional[Dict[str, Any]]:
    tpl = _load_template(_TEMPLATE_CHAIN)
    prompt = _render(
        tpl,
        {
            "tags": tags_csv,
            "description": _truncate(description, 12000),
            "correct_solution": _truncate(correct_code, _MAX_CODE_CHARS),
        },
    )
    try:
        role_cfg = UnifiedLLMClient.build_role_config(config, "code")
    except Exception as e:
        logger.warning("evolution_llm: bad LLM config: %s", e)
        return None
    llm = UnifiedLLMClient(role_cfg)
    if not llm.is_initialized:
        logger.warning("evolution_llm: LLM client not initialized")
        return None
    raw = llm.generate(prompt, temperature=float(role_cfg.get("temperature", 0.2)))
    return parse_json_object(raw or "")


def run_logic_diff(
    config: Dict[str, Any],
    *,
    description: str,
    tags_csv: str,
    correct_code: str,
    incorrect_code: str,
    logic_analysis: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    tpl = _load_template(_TEMPLATE_DIFF)
    la_str = json.dumps(logic_analysis, ensure_ascii=False)
    prompt = _render(
        tpl,
        {
            "tags": tags_csv,
            "description": _truncate(description, 12000),
            "correct_solution": _truncate(correct_code, _MAX_CODE_CHARS),
            "incorrect_solution": _truncate(incorrect_code, _MAX_CODE_CHARS),
            "logic_analysis": _truncate(la_str, 24000),
        },
    )
    try:
        role_cfg = UnifiedLLMClient.build_role_config(config, "code")
    except Exception as e:
        logger.warning("evolution_llm: bad LLM config: %s", e)
        return None
    llm = UnifiedLLMClient(role_cfg)
    if not llm.is_initialized:
        return None
    raw = llm.generate(prompt, temperature=float(role_cfg.get("temperature", 0.2)))
    return parse_json_object(raw or "")
