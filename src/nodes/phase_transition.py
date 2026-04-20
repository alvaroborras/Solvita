"""Phase Transition Node — Phase 切换

在 Phase 之间的跨越点插入此节点。
职责：更新 `current_phase`，供顶层 Orchestrator 路由使用。
对话历史（messages）全流程保留，不在 phase 切换时清空。
"""

from typing import Dict, Any, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

def _next_phase(state: "SolvitaState") -> str:
    current = state.get("current_phase", "ABSTRACT")
    if current == "ABSTRACT":
        return "TESTGEN"
    if current == "TESTGEN":
        return "CODEGEN"
    if current == "CODEGEN":
        return "HACKER"
    if current == "HACKER":
        # This node is only reached from HACKER on the loop-back path.
        return "CODEGEN"
    return current


def phase_transition_node(state: "SolvitaState") -> Dict[str, Any]:
    """推进 current_phase，保留 LLM 对话历史。"""
    current = state.get("current_phase", "ABSTRACT")
    next_phase = _next_phase(state)

    update: Dict[str, Any] = {
        "current_phase": next_phase,
        "execution_log": [f"Phase transition: {current} → {next_phase}"],
    }

    if current == "HACKER":
        update["hack_round"] = 0
        if not state.get("hack_passed", True):
            # A failed hack sends the workflow back to CodeGen for another repair round.
            update["iteration"] = state.get("iteration", 0) + 1
            update["status"] = "pending"

    logger.info(
        f"[Orchestrator] Phase transition: {current} → {next_phase} | "
        f"messages preserved ({len(state.get('messages', []))} items)"
    )

    return update
