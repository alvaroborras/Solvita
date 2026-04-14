"""Abstract problem node — canonical representation + whitelist tags + confidence/trace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import yaml
from loguru import logger

from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.memory import MemoryClient, MemoryNamespace
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


def load_tag_whitelist(config: Dict[str, Any]) -> List[str]:
    """Load allowed tags (lowercase) from config path or default ``config/tag_whitelist.yaml``."""
    override = (config.get("tag_whitelist_path") or "").strip()
    path = Path(override) if override else CONFIG_DIR / "tag_whitelist.yaml"
    if not path.is_file():
        logger.warning("[Abstract] tag whitelist file missing at %s; using empty whitelist", path)
        return []
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tags = data.get("tags") or []
    out: List[str] = []
    for t in tags:
        s = str(t).strip().lower()
        if s:
            out.append(s)
    return out


def _filter_tags(raw_tags: Any, whitelist: List[str]) -> List[str]:
    if not whitelist:
        return []
    allow = set(whitelist)
    result: List[str] = []
    if not isinstance(raw_tags, list):
        return result
    for t in raw_tags:
        key = str(t).strip().lower().replace(" ", "_")
        if key in allow and key not in result:
            result.append(key)
    return result


def _build_abstract_messages(
    problem_desc: str,
    problem_types: List[str],
    constraints: Dict[str, Any],
    tag_whitelist: List[str],
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
    whitelist_s = ", ".join(tag_whitelist) if tag_whitelist else "(empty — emit algorithmic_tags: [])"
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
        },
    )
    if advice_block:
        user += f"\n\nPlanning memory hints:\n{advice_block}\n"
    return system_t.strip(), user.strip()


def abstract_problem_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Produce canonical problem data, whitelist-filtered tags, confidence, and trace.
    Also fills plan.algorithm_choice and plan.implementation_steps for codegen.
    """
    logger.info("[Node] Abstract problem (canonical + tags)")

    cfg = state["config"]
    templates = load_prompt_templates()
    tag_whitelist = load_tag_whitelist(cfg)

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

    for attempt in range(2):
        system_msg, user_msg = _build_abstract_messages(
            problem_desc,
            problem_types,
            constraints,
            tag_whitelist,
            advice.strip() if advice else "",
            templates,
            compact=prompt_compact,
        )
        try:
            response = llm.generate_with_system(system_msg, user_msg)
        except PromptTooLongError:
            if prompt_compact:
                raise
            prompt_compact = True
            logger.warning("[Abstract] Prompt exceeded max tokens, retrying with compact prompt")
            continue
        llm_calls += 1
        last_response = response
        try:
            parsed = parse_json_response(response)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                logger.warning("[Abstract] JSON parse failed, retrying...")
            else:
                logger.warning("[Abstract] JSON parse failed twice; using fallbacks")

    canonical_problem: Dict[str, Any] = {}
    algorithmic_tags: List[str] = []
    algorithm_choice = "Structured implementation from canonical"
    implementation_steps = [
        "Derive the solution from the canonical objective and constraints.",
        "Implement carefully with respect to limits.",
        "Validate edge cases listed in canonical_problem.edge_cases.",
    ]
    abstract_confidence = 0.35
    abstract_trace: Dict[str, Any] = {
        "source": "llm",
        "notes": [],
    }

    if parsed:
        canonical_problem = parsed.get("canonical_problem") or {}
        if not isinstance(canonical_problem, dict):
            canonical_problem = {}
        raw_tags = parsed.get("algorithmic_tags", [])
        algorithmic_tags = _filter_tags(raw_tags, tag_whitelist)
        algorithm_choice = str(parsed.get("algorithm_choice") or algorithm_choice).strip() or algorithm_choice
        steps = parsed.get("implementation_steps")
        if isinstance(steps, list) and steps:
            implementation_steps = [str(s) for s in steps if str(s).strip()]
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
            "algorithm_choice": algorithm_choice,
            "implementation_steps": implementation_steps,
            "abstract_only": True,
        },
        "algorithm_choice": algorithm_choice,
        "implementation_steps": implementation_steps,
        "memory_item_ids": memory_item_ids,
        "memory_advice": advice.strip() if advice else "",
    }

    if algorithmic_tags:
        canonical_problem = dict(canonical_problem)
        canonical_problem["tags"] = algorithmic_tags

    return {
        "problem": {
            "canonical": canonical_problem,
            "tags_selected": algorithmic_tags,
            "abstract_confidence": abstract_confidence,
            "abstract_trace": abstract_trace,
        },
        "plan": plan,
        "execution_log": [
            f"Abstract problem: confidence={abstract_confidence:.2f}, tags={algorithmic_tags}",
            f"  Memory items injected: {len(memory_item_ids)}",
        ],
        "llm_calls": llm_calls,
    }
