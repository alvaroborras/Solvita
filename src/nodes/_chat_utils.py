"""Shared helper for multi-turn LLM calls that read/write state["messages"]."""

import json
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from loguru import logger

from src.llm import UnifiedLLMClient
from src.llm.token_usage import estimate_message_tokens, get_token_usage_snapshot


class ChatCompactionContext(TypedDict, total=False):
    current_phase: str
    iteration: int
    max_iterations: int
    problem_description: str
    current_objective: str
    memory_advice: str
    solver_graph_augmentation_block: str
    skill_selection_skill_ids: List[str]
    skill_selection_skills_content_md: str
    feedback_summary: str
    recent_failures: List[Dict[str, Any]]
    hack_result: str
    hack_failure_type: str
    generator_route_used: str
    generator_failure_kind: str
    generator_failure_reason: str
    execution_log_tail: List[str]
    node_name: str


class ChatCompactionResult(TypedDict, total=False):
    compacted_messages: List[Dict[str, str]]
    persisted_messages: List[Dict[str, str]]
    did_compact: bool
    removed_message_count: int
    preserved_recent_count: int
    summary_text: str
    estimated_tokens_before: int
    estimated_tokens_after: int
    trigger_reason: str


def _get_message_compaction_settings(config: Optional[Dict[str, Any]], *, llm_max_tokens: int) -> Dict[str, Any]:
    raw = (config or {}).get("message_compaction", {})
    ratio = float(raw.get("max_history_ratio", 0.5) or 0.5)
    return {
        "enabled": bool(raw.get("enabled", True)),
        "max_history_tokens": int(llm_max_tokens * ratio),
        "preserve_recent_messages": int(raw.get("preserve_recent_messages", 8) or 8),
        "cumulative_prompt_tokens_threshold": int(raw.get("cumulative_prompt_tokens_threshold", 120000) or 120000),
        "max_summary_chars": int(raw.get("max_summary_chars", 4000) or 4000),
        "max_summary_lines": int(raw.get("max_summary_lines", 40) or 40),
    }


def build_chat_compaction_context(state: Dict[str, Any], *, node_name: str | None = None) -> ChatCompactionContext:
    plan = state.get("plan", {}) if isinstance(state.get("plan", {}), dict) else {}
    feedback = state.get("feedback", {}) if isinstance(state.get("feedback", {}), dict) else {}
    feedback_payload = feedback.get("feedback", {}) if isinstance(feedback.get("feedback", {}), dict) else {}
    problem = state.get("problem", {}) if isinstance(state.get("problem", {}), dict) else {}
    canonical = problem.get("canonical", {}) if isinstance(problem.get("canonical", {}), dict) else {}
    objective = canonical.get("objective") or problem.get("description", "")
    execution_log = state.get("execution_log", [])
    if not isinstance(execution_log, list):
        execution_log = []

    return {
        "current_phase": state.get("current_phase", ""),
        "iteration": state.get("iteration", 0),
        "max_iterations": state.get("max_iterations", 0),
        "problem_description": problem.get("description", ""),
        "current_objective": objective,
        "memory_advice": plan.get("memory_advice", ""),
        "solver_graph_augmentation_block": plan.get("solver_graph_augmentation_block", ""),
        "skill_selection_skill_ids": list(plan.get("skill_selection_skill_ids", []) or []),
        "skill_selection_skills_content_md": plan.get("skill_selection_skills_content_md", ""),
        "feedback_summary": feedback_payload.get("analysis", ""),
        "recent_failures": list(feedback_payload.get("failures", []) or []),
        "hack_result": state.get("hack_result", ""),
        "hack_failure_type": state.get("hack_failure_type", ""),
        "generator_route_used": state.get("generator_route_used", ""),
        "generator_failure_kind": state.get("generator_failure_kind", ""),
        "generator_failure_reason": state.get("generator_failure_reason", ""),
        "execution_log_tail": [str(item) for item in execution_log[-5:]],
        "node_name": node_name or "",
    }


def should_compact_history(
    messages: List[Dict[str, str]],
    *,
    settings: Dict[str, Any],
    model: str,
    config: Optional[Dict[str, Any]],
) -> tuple[bool, str, int]:
    estimated_tokens = estimate_message_tokens(messages, model=model)
    if estimated_tokens > settings["max_history_tokens"]:
        return True, "size", estimated_tokens

    usage = get_token_usage_snapshot(config or {})
    if usage.get("prompt_tokens", 0) >= settings["cumulative_prompt_tokens_threshold"]:
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) > settings["preserve_recent_messages"] + 1:
            return True, "cumulative_usage", estimated_tokens

    return False, "", estimated_tokens


def partition_history_for_compaction(
    messages: List[Dict[str, str]],
    preserve_recent_messages: int,
) -> tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    system_messages = [m for m in messages if m.get("role") == "system"]
    other_messages = [m for m in messages if m.get("role") != "system"]
    if len(other_messages) <= preserve_recent_messages:
        return system_messages, [], other_messages

    split = len(other_messages) - preserve_recent_messages
    return system_messages, other_messages[:split], other_messages[split:]


def _bound_summary_text(summary_text: str, *, max_chars: int, max_lines: int) -> str:
    lines = [line.rstrip() for line in summary_text.splitlines() if line.strip()]
    bounded = "\n".join(lines[:max_lines])
    if len(bounded) > max_chars:
        bounded = bounded[: max_chars - 3].rstrip() + "..."
    return bounded


def build_structured_compaction_summary(
    llm: UnifiedLLMClient,
    older_messages: List[Dict[str, str]],
    context: Optional[ChatCompactionContext],
    *,
    settings: Dict[str, Any],
) -> str:
    context_json = json.dumps(context or {}, ensure_ascii=False, indent=2)
    transcript_json = json.dumps(older_messages, ensure_ascii=False, indent=2)
    prompt = (
        "Summarize the older Solvita transcript for continuation.\n"
        "Fill these sections even if the value is none known: Problem state, Current objective, "
        "Important failure evidence, Active hypotheses, Disproved hypotheses, Prior repair attempts, "
        "Solver-network knowledge used, Skills selected, Continuation constraints.\n"
        "Prefer explicit state over stale transcript guesses.\n\n"
        f"Structured state:\n{context_json}\n\n"
        f"Older transcript:\n{transcript_json}"
    )
    raw = llm.chat([{"role": "user", "content": prompt}])
    bounded = _bound_summary_text(
        raw,
        max_chars=settings["max_summary_chars"],
        max_lines=settings["max_summary_lines"],
    )
    return (
        "This conversation is being continued with compacted prior context.\n"
        "The summary below covers older messages; recent messages are preserved verbatim.\n\n"
        "<solvita_compaction_summary>\n"
        f"{bounded}\n"
        "</solvita_compaction_summary>"
    )


def compact_history(
    llm: UnifiedLLMClient,
    messages: List[Dict[str, str]],
    *,
    context: Optional[ChatCompactionContext],
    settings: Dict[str, Any],
    config: Optional[Dict[str, Any]],
) -> ChatCompactionResult:
    should_compact, trigger_reason, estimated_before = should_compact_history(
        messages,
        settings=settings,
        model=llm.model,
        config=config,
    )
    if not should_compact:
        return {
            "compacted_messages": messages,
            "persisted_messages": messages,
            "did_compact": False,
            "estimated_tokens_before": estimated_before,
            "estimated_tokens_after": estimated_before,
        }

    system_messages = [m for m in messages if m.get("role") == "system"]
    live_message = messages[-1] if messages and messages[-1].get("role") == "user" else None
    history_messages = messages[:-1] if live_message is not None else messages

    _, older_messages, recent_messages = partition_history_for_compaction(
        history_messages,
        settings["preserve_recent_messages"],
    )
    if not older_messages:
        return {
            "compacted_messages": messages,
            "persisted_messages": messages,
            "did_compact": False,
            "estimated_tokens_before": estimated_before,
            "estimated_tokens_after": estimated_before,
        }

    summary_message = {
        "role": "system",
        "content": build_structured_compaction_summary(llm, older_messages, context, settings=settings),
    }
    persisted_messages = system_messages + [summary_message] + recent_messages
    compacted_messages = list(persisted_messages)
    if live_message is not None:
        compacted_messages.append(live_message)

    estimated_after = estimate_message_tokens(compacted_messages, model=llm.model)
    logger.info(
        "[ChatHistory] Compacted history trigger=%s before=%d after=%d removed=%d preserved_recent=%d summary_chars=%d",
        trigger_reason,
        estimated_before,
        estimated_after,
        len(older_messages),
        len(recent_messages),
        len(summary_message["content"]),
    )
    return {
        "compacted_messages": compacted_messages,
        "persisted_messages": persisted_messages,
        "did_compact": True,
        "removed_message_count": len(older_messages),
        "preserved_recent_count": len(recent_messages),
        "summary_text": summary_message["content"],
        "estimated_tokens_before": estimated_before,
        "estimated_tokens_after": estimated_after,
        "trigger_reason": trigger_reason,
    }


def normalize_chat_history_result(
    result: Any,
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
    if isinstance(result, tuple) and len(result) == 3:
        response, new_messages, persisted_messages = result
        return str(response), list(new_messages), list(persisted_messages)
    raise TypeError("chat_with_history must return (response, new_messages, persisted_messages)")


def chat_with_history(
    llm: UnifiedLLMClient,
    messages_history: List[Dict[str, str]],
    user_content: str,
    system_content: Optional[str] = None,
    max_history_tokens: Optional[int] = None,
    compaction_context: Optional[ChatCompactionContext] = None,
    compaction_config: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
    """Call LLM with full conversation history and return persisted rewritten history.

    Returns
    -------
    (response_text, new_messages, persisted_messages) where persisted_messages is the
    full transcript that should replace ``state["messages"]``.
    """
    msgs = list(messages_history)
    settings = _get_message_compaction_settings(compaction_config, llm_max_tokens=llm.max_tokens)
    if max_history_tokens is not None:
        settings["max_history_tokens"] = max_history_tokens

    if system_content and not any(m.get("role") == "system" for m in msgs):
        msgs.insert(0, {"role": "system", "content": system_content})

    msgs.append({"role": "user", "content": user_content})

    compacted = compact_history(
        llm,
        msgs,
        context=compaction_context,
        settings=settings,
        config=compaction_config,
    )
    response = llm.chat(compacted["compacted_messages"], **kwargs)

    new_messages = [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": response},
    ]
    persisted_messages = list(compacted["persisted_messages"])
    persisted_messages.extend(new_messages)
    return response, new_messages, persisted_messages
