"""Abstract problem node — canonical representation + whitelist tags + confidence/trace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, TYPE_CHECKING

import yaml
from loguru import logger

from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.memory import MemoryClient, MemoryNamespace
from src.nodes._chat_utils import chat_with_history
from src.utils.json_utils import parse_json_response
from src.utils.prompt_templates import (
    get_nested_template,
    load_prompt_templates,
    render_placeholders,
)
from src.utils.prompt_utils import compact_json_for_prompt, truncate_for_prompt

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class TagWhitelistBundle(NamedTuple):
    """Merged allow-list plus Q-node level-1 / level-2 vocabularies for prompting."""

    merged: List[str]
    tags_level1: List[str]
    tags_level2: List[str]


def _normalize_whitelist_token(raw: str) -> str:
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def load_tag_whitelist_bundle(config: Dict[str, Any]) -> TagWhitelistBundle:
    """
    Load tags from ``config/tag_whitelist.yaml`` (or ``tag_whitelist_path`` override).

    Accepts legacy flat ``tags`` and/or ``tags_level1`` + ``tags_level2`` (solver-network Q fields).
    ``merged`` is the sorted union of level-1 and level-2 vocab (prompt reference only).
    """
    override = (config.get("tag_whitelist_path") or "").strip()
    path = Path(override) if override else CONFIG_DIR / "tag_whitelist.yaml"
    if not path.is_file():
        logger.warning("[Abstract] tag whitelist file missing at %s; using empty whitelist", path)
        return TagWhitelistBundle(merged=[], tags_level1=[], tags_level2=[])
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    def collect(seq: Any) -> List[str]:
        out: List[str] = []
        if not isinstance(seq, list):
            return out
        for t in seq:
            s = _normalize_whitelist_token(str(t))
            if s:
                out.append(s)
        return out

    legacy = collect(data.get("tags"))
    l1 = collect(data.get("tags_level1"))
    l2 = collect(data.get("tags_level2"))

    seen: set[str] = set()
    merged_list: List[str] = []
    for bucket in (legacy, l1, l2):
        for s in bucket:
            if s not in seen:
                seen.add(s)
                merged_list.append(s)
    merged_list.sort()

    # Dedupe level lists while preserving file order for prompts
    def uniq(seq: List[str]) -> List[str]:
        s2: set[str] = set()
        out2: List[str] = []
        for x in seq:
            if x not in s2:
                s2.add(x)
                out2.append(x)
        return out2

    return TagWhitelistBundle(
        merged=merged_list,
        tags_level1=uniq(l1),
        tags_level2=uniq(l2),
    )


def load_tag_whitelist(config: Dict[str, Any]) -> List[str]:
    """Backward-compatible: merged allow-list only."""
    return load_tag_whitelist_bundle(config).merged


def _filter_tags(raw_tags: Any, whitelist: List[str]) -> List[str]:
    if not whitelist:
        return []
    allow = set(whitelist)
    result: List[str] = []
    if not isinstance(raw_tags, list):
        return result
    for t in raw_tags:
        key = _normalize_whitelist_token(str(t))
        if key in allow and key not in result:
            result.append(key)
    return result


def _parse_algorithmic_tags_from_llm(
    parsed: Optional[Dict[str, Any]],
    bundle: TagWhitelistBundle,
) -> tuple[List[str], List[str]]:
    """
    Parse level-1 / level-2 tag lists from LLM JSON.

    Prefer ``algorithmic_tags_level1`` / ``algorithmic_tags_level2``. If absent, accept legacy
    ``algorithmic_tags`` and route each token into level-1 or level-2 by whitelist membership.
    """
    if not parsed or not isinstance(parsed, dict):
        return [], []

    allow1 = set(bundle.tags_level1)
    allow2 = set(bundle.tags_level2)

    raw_l1 = parsed.get("algorithmic_tags_level1")
    raw_l2 = parsed.get("algorithmic_tags_level2")
    if raw_l1 is not None or raw_l2 is not None:
        return (
            _filter_tags(raw_l1 or [], bundle.tags_level1),
            _filter_tags(raw_l2 or [], bundle.tags_level2),
        )

    legacy = parsed.get("algorithmic_tags")
    if not isinstance(legacy, list) or not legacy:
        return [], []

    out1: List[str] = []
    out2: List[str] = []
    for t in legacy:
        key = _normalize_whitelist_token(str(t))
        if not key:
            continue
        if key in allow1 and key not in out1:
            out1.append(key)
        elif key in allow2 and key not in out2:
            out2.append(key)
    return out1, out2


def _build_abstract_messages(
    problem_desc: str,
    problem_types: List[str],
    constraints: Dict[str, Any],
    tag_bundle: TagWhitelistBundle,
    advice: str,
    templates: Dict[str, Any],
    compact: bool,
) -> tuple[str, str]:
    system_t = get_nested_template(templates, "abstract_problem.system")
    user_t = get_nested_template(templates, "abstract_problem.user")
    if not isinstance(system_t, str) or not isinstance(user_t, str):
        raise KeyError("abstract_problem templates must be strings")

    desc_chars = 12000 if not compact else 6000
    constraint_chars = 3000 if not compact else 1500
    advice_chars = 4000 if not compact else 1500
    compact_problem_desc = truncate_for_prompt(problem_desc, desc_chars, "PROBLEM_DESC")
    compact_constraints = compact_json_for_prompt(constraints, constraint_chars, "CONSTRAINTS")
    types_s = ", ".join(problem_types[:8]) if problem_types else "Not specified"
    merged = tag_bundle.merged
    l1 = tag_bundle.tags_level1
    l2 = tag_bundle.tags_level2
    if compact:
        whitelist_s = ", ".join(merged[:120]) + (" …" if len(merged) > 120 else "")
        wl1_s = ", ".join(l1[:40]) + (" …" if len(l1) > 40 else "")
        wl2_s = ", ".join(l2[:80]) + (" …" if len(l2) > 80 else "")
    else:
        whitelist_s = ", ".join(merged) if merged else "(empty — emit algorithmic_tags: [])"
        wl1_s = ", ".join(l1) if l1 else "(none)"
        wl2_s = ", ".join(l2) if l2 else "(none)"
    advice_block = ""
    if advice:
        advice_block = truncate_for_prompt(advice, advice_chars, "PLAN_MEMORY_ADVICE")

    user = render_placeholders(
        user_t,
        {
            "PROBLEM_DESC": compact_problem_desc,
            "PROBLEM_TYPES": types_s,
            "CONSTRAINTS_JSON": compact_constraints,
            "TAG_WHITELIST": whitelist_s,
            "TAG_WHITELIST_LEVEL1": wl1_s,
            "TAG_WHITELIST_LEVEL2": wl2_s,
        },
    )
    if advice_block:
        user += f"\n\nPlanning memory hints:\n{advice_block}\n"
    return system_t.strip(), user.strip()


def abstract_problem_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Produce canonical problem data, whitelist-filtered tags, confidence, and trace.
    Does not set algorithm choice or implementation steps; those come from ``solver_skill_plan_node`` when enabled.
    """
    logger.info("[Node] Abstract problem (canonical + tags)")

    cfg = state["config"]
    templates = load_prompt_templates()
    tag_bundle = load_tag_whitelist_bundle(cfg)

    llm = UnifiedLLMClient(cfg)
    problem_desc = state["problem"].get("description", "")
    problem_types = state["problem"].get("types", [])
    constraints = state["problem"].get("constraints", {})
    iteration = state.get("iteration", 0)

    memory = MemoryClient(
        namespace=MemoryNamespace.PLAN,
        config=cfg,
        problem_desc=problem_desc,
        canonical={},
    )

    failure_type = None
    if iteration > 0:
        feedback_data = state.get("feedback", {}).get("feedback", {})
        error_pattern = feedback_data.get("error_pattern", "")
        if "tle" in error_pattern.lower() or "timeout" in error_pattern.lower():
            failure_type = "TIMEOUT"
        elif "compile" in error_pattern.lower():
            failure_type = "COMPILE_FAIL"
        elif error_pattern:
            failure_type = "SOLVE_WA"

    advice, memory_item_ids = memory.get_injection(
        fsm_state="SOLVE_DRAFT",
        failure_type=failure_type,
        attempt_count=iteration,
    )

    prompt_compact = False
    llm_calls = 0
    parsed: Optional[Dict[str, Any]] = None
    last_response = ""
    all_new_messages: List[Dict[str, str]] = []
    history = list(state.get("messages", []))

    for attempt in range(2):
        system_msg, user_msg = _build_abstract_messages(
            problem_desc,
            problem_types,
            constraints,
            tag_bundle,
            advice.strip() if advice else "",
            templates,
            compact=prompt_compact,
        )
        try:
            try:
                response, new_msgs = chat_with_history(
                    llm, history, user_msg,
                    system_content=system_msg,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                logger.warning(
                    "[Abstract] response_format=json_object failed (%s), retrying without",
                    e,
                )
                response, new_msgs = chat_with_history(
                    llm, history, user_msg,
                    system_content=system_msg,
                )
        except PromptTooLongError:
            if prompt_compact:
                raise
            prompt_compact = True
            logger.warning("[Abstract] Prompt exceeded max tokens, retrying with compact prompt")
            continue
        llm_calls += 1
        last_response = response
        all_new_messages.extend(new_msgs)
        history.extend(new_msgs)
        try:
            parsed = parse_json_response(response)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                logger.warning("[Abstract] JSON parse failed, retrying...")
            else:
                logger.warning("[Abstract] JSON parse failed twice; using fallbacks")

    canonical_problem: Dict[str, Any] = {}
    tags_level1: List[str] = []
    tags_level2: List[str] = []
    abstract_confidence = 0.35
    abstract_trace: Dict[str, Any] = {
        "source": "llm",
        "notes": [],
    }

    if parsed:
        canonical_problem = parsed.get("canonical_problem") or {}
        if not isinstance(canonical_problem, dict):
            canonical_problem = {}
        tags_level1, tags_level2 = _parse_algorithmic_tags_from_llm(parsed, tag_bundle)
        try:
            abstract_confidence = float(parsed.get("abstract_confidence", abstract_confidence))
        except (TypeError, ValueError):
            abstract_confidence = 0.35
        abstract_confidence = max(0.0, min(1.0, abstract_confidence))
        tr = parsed.get("abstract_trace")
        if isinstance(tr, dict):
            abstract_trace = {"source": "llm", **tr}
        elif isinstance(tr, str):
            abstract_trace = {"source": "llm", "rationale": tr}
    else:
        abstract_trace = {
            "source": "fallback",
            "notes": ["Failed to parse abstract JSON; using minimal defaults."],
            "raw_response_excerpt": last_response[:800],
        }

    plan = {
        "solution_plan": {
            "abstract_only": True,
        },
        "algorithm_choice": "",
        "implementation_steps": [],
        "memory_item_ids": memory_item_ids,
        "memory_advice": advice.strip() if advice else "",
    }

    if tags_level1 or tags_level2:
        canonical_problem = dict(canonical_problem)
        if tags_level1:
            canonical_problem["tags"] = tags_level1
        if tags_level2:
            canonical_problem["tags_level2"] = tags_level2

    return {
        "problem": {
            "canonical": canonical_problem,
            "tags_selected": tags_level1,
            "tags_level2_selected": tags_level2,
            "abstract_confidence": abstract_confidence,
            "abstract_trace": abstract_trace,
        },
        "plan": plan,
        "messages": all_new_messages,
        "execution_log": [
            (
                f"Abstract problem: confidence={abstract_confidence:.2f}, "
                f"tags_l1={tags_level1}, tags_l2={tags_level2}"
            ),
            f"  Memory items injected: {len(memory_item_ids)}",
        ],
        "llm_calls": llm_calls,
    }
