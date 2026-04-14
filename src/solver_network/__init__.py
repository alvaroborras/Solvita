"""Optional skill-graph rollout adapter for one-shot codegen injection."""

from .adapter import build_solver_network_block
from .planner_input import build_planner_input_from_state

__all__ = ["build_solver_network_block", "build_planner_input_from_state"]
