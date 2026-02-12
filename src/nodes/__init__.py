"""Nodes module - Each node in a separate file with integrated logic"""

# Use lazy imports to avoid circular dependencies
# The workflow module imports from here, but these modules import from state
# which in turn may import from workflow (via graph/__init__.py)

def __getattr__(name: str):
    if name == "retrieve_knowledge_node":
        from .retrieve_knowledge import retrieve_knowledge_node
        return retrieve_knowledge_node
    elif name == "plan_solution_node":
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "retrieve_knowledge_node",
    "plan_solution_node",
    "generate_tests_node",
    "generate_code_node",
    "compile_code_node",
    "run_tests_node",
    "analyze_feedback_node",
    "unified_check_node",
    "status_routing",
    "compilation_routing",
    "hack_test_node",
    "hack_routing",
]

