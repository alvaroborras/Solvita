"""Phase Transition Node — Token 截断与 Phase 切换

在 Phase 1 → Phase 2 和 Phase 2 → Phase 3 的跨越点插入此节点。
它的唯一职责：
  1. 清空 `messages`（大模型对话历史），防止跨 Phase LLM Token 爆炸。
  2. 更新 `current_phase`，供顶层 Orchestrator 路由使用。

注意：所有实体资产（测试文件 .in/.out、可执行文件路径）均通过 state 中的
文件路径字段（checker_exe、validator_exe、executable_path 等）传递，
本节点不会删除任何硬盘文件。
"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

_PHASE_SEQUENCE = {
    "TESTGEN": "CODEGEN",
    "CODEGEN": "HACKER",
    "HACKER": "DONE",
}


def phase_transition_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    清空 LLM messages，推进 current_phase。

    LangGraph 的 add_messages reducer 在接收到空列表时会清空历史，
    因此直接返回 ``"messages": []`` 即可实现硬性清空。
    """
    current = state.get("current_phase", "TESTGEN")
    next_phase = _PHASE_SEQUENCE.get(current, "DONE")

    logger.info(
        f"[Orchestrator] Phase transition: {current} → {next_phase} | "
        f"messages cleared ({len(state.get('messages', []))} items dropped)"
    )

    return {
        "messages": [],          # 硬性清空 LLM 对话历史
        "current_phase": next_phase,
        "execution_log": [f"Phase transition: {current} → {next_phase} (messages cleared)"],
    }
