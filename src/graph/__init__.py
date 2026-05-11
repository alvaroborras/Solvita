"""LangGraph workflow module for Solvita Agent"""

from src.graph.state import SolvitaState, create_initial_state


def __getattr__(name: str):
    """Lazy import workflow to avoid circular dependency with nodes."""
    if name == "create_solvita_workflow":
        from src.graph.workflow import create_solvita_workflow
        return create_solvita_workflow
    elif name == "run_workflow":
        from src.graph.workflow import run_workflow
        return run_workflow
    elif name == "stream_workflow":
        from src.graph.workflow import stream_workflow
        return stream_workflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SolvitaState",
    "create_initial_state",
    "create_solvita_workflow",
    "run_workflow",
    "stream_workflow",
]
