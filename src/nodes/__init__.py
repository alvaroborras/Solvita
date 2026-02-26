"""Nodes module - Each node in a separate file with integrated logic"""

# Use lazy imports to avoid circular dependencies
# The workflow module imports from here, but these modules import from state
# which in turn may import from workflow (via graph/__init__.py)

def __getattr__(name: str):
    if name == "plan_solution_node":
        from .plan_solution import plan_solution_node
        return plan_solution_node
    elif name == "generate_tests_node":
        from .generate_tests import generate_tests_node
        return generate_tests_node
    elif name == "generate_code_node":
        from .generate_code import generate_code_node
        return generate_code_node
    elif name == "compile_code_node":
        from .compile_code import compile_code_node
        return compile_code_node
    elif name == "run_tests_node":
        from .run_tests import run_tests_node
        return run_tests_node
    elif name == "analyze_feedback_node":
        from .analyze_feedback import analyze_feedback_node
        return analyze_feedback_node
    elif name == "unified_check_node":
        from .unified_check import unified_check_node
        return unified_check_node
    elif name == "update_plan_memory_node":
        from .update_plan_memory import update_plan_memory_node
        return update_plan_memory_node
    elif name == "update_solve_memory_node":
        from .update_solve_memory import update_solve_memory_node
        return update_solve_memory_node
    elif name == "update_test_memory_node":
        from .update_test_memory import update_test_memory_node
        return update_test_memory_node
    elif name == "update_oracle_memory_node":
        from .update_oracle_memory import update_oracle_memory_node
        return update_oracle_memory_node
    elif name == "phase_transition_node":
        from .phase_transition import phase_transition_node
        return phase_transition_node
    elif name == "update_hacker_memory_node":
        from .update_hacker_memory import update_hacker_memory_node
        return update_hacker_memory_node
    elif name == "status_routing":
        from .routing import status_routing
        return status_routing
    elif name == "compilation_routing":
        from .routing import compilation_routing
        return compilation_routing
    elif name == "hack_test_node":
        from .hack_test import hack_test_node
        return hack_test_node
    elif name == "hack_routing":
        from .routing import hack_routing
        return hack_routing
    elif name == "hack_outcome_routing":
        from .routing import hack_outcome_routing
        return hack_outcome_routing
    elif name == "join_ready_node":
        from .join_ready import join_ready_node
        return join_ready_node
    elif name == "join_wait_node":
        from .join_ready import join_wait_node
        return join_wait_node
    elif name == "join_routing":
        from .routing import join_routing
        return join_routing
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "plan_solution_node",
    "generate_tests_node",
    "generate_code_node",
    "compile_code_node",
    "run_tests_node",
    "analyze_feedback_node",
    "unified_check_node",
    "update_plan_memory_node",
    "update_solve_memory_node",
    "update_test_memory_node",
    "update_oracle_memory_node",
    "phase_transition_node",
    "update_hacker_memory_node",
    "status_routing",
    "compilation_routing",
    "hack_test_node",
    "hack_routing",
    "hack_outcome_routing",
    "join_ready_node",
    "join_wait_node",
    "join_routing",
]
