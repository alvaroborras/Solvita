"""Shared helper for multi-turn LLM calls that read/write state["messages"]."""

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from src.llm import UnifiedLLMClient
from src.llm.token_usage import estimate_message_tokens


def _trim_history(
    messages: List[Dict[str, str]],
    max_tokens: int,
    model: str,
) -> List[Dict[str, str]]:
    """Drop oldest non-system messages until estimated tokens < max_tokens."""
    est = estimate_message_tokens(messages, model=model)
    if est <= max_tokens:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]

    while other_msgs and estimate_message_tokens(system_msgs + other_msgs, model=model) > max_tokens:
        dropped = other_msgs.pop(0)
        logger.debug("[ChatHistory] Dropped oldest message (role=%s, len=%d)", dropped.get("role"), len(str(dropped.get("content", ""))))

    return system_msgs + other_msgs


def chat_with_history(
    llm: UnifiedLLMClient,
    messages_history: List[Dict[str, str]],
    user_content: str,
    system_content: Optional[str] = None,
    max_history_tokens: Optional[int] = None,
    **kwargs: Any,
) -> Tuple[str, List[Dict[str, str]]]:
    """Call LLM with full conversation history, return (response, new_messages_to_append).

    Parameters
    ----------
    llm : UnifiedLLMClient
    messages_history : current state["messages"]
    user_content : the new user prompt
    system_content : optional system message (inserted at position 0 if no system msg exists yet)
    max_history_tokens : safety cap; defaults to 70% of llm.max_tokens
    **kwargs : forwarded to llm.chat() (e.g. response_format, temperature)

    Returns
    -------
    (response_text, new_messages) where new_messages should be returned via
    ``{"messages": new_messages}`` so the add_messages reducer appends them.
    """
    msgs = list(messages_history)

    if system_content and not any(m.get("role") == "system" for m in msgs):
        msgs.insert(0, {"role": "system", "content": system_content})

    msgs.append({"role": "user", "content": user_content})

    cap = max_history_tokens or int(llm.max_tokens * 0.7)
    msgs = _trim_history(msgs, cap, llm.model)

    response = llm.chat(msgs, **kwargs)

    new_messages = [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": response},
    ]
    return response, new_messages
