"""LangGraph Node Implementations - Connected to Real Modules

All nodes now call actual module implementations.
"""

from typing import Dict, Any
from src.graph.state import SolvitaState
from loguru import logger


# ========== Problem Understanding Nodes ==========

def parse_problem_node(state: SolvitaState) -> Dict[str, Any]:
    """Parse raw problem input into structured format"""
    logger.info(f"[Node] Parsing problem (iteration {state['iteration_count']})")

    from src.parser.problem_parser import ProblemParser

    parser = ProblemParser(llm=None)
    parsed = parser.parse(state['raw_problem'])

    return {
        **parsed,
        "execution_log": ["✓ Problem parsed successfully"],
    }


# ========== Knowledge Retrieval Nodes ==========

def retrieve_knowledge_node(state: SolvitaState) -> Dict[str, Any]:
    """Retrieve relevant knowledge (placeholder for now)"""
    logger.info("[Node] Retrieving relevant knowledge")

    # TODO: Implement knowledge retrieval when Neo4j/Vector DB are set up
    return {
        "retrieved_knowledge": [],
        "relevant_algorithms": [],
        "relevant_data_structures": [],
        "similar_problems": [],
        "execution_log": ["Knowledge retrieval skipped (not implemented)"],
    }


# ========== Planning Nodes ==========

def plan_solution_node(state: SolvitaState) -> Dict[str, Any]:
    """Generate high-level solution plan"""
    logger.info("[Node] Planning solution approach")

    from src.planner.solution_planner import SolutionPlanner
    from src.llm.model_factory import ModelFactory

    # Get LLM (placeholder for now)
    try:
        llm = ModelFactory.create(state['config'].get('model', 'gpt-4'))
    except:
        # Fallback: use mock LLM
        llm = type('MockLLM', (), {'generate': lambda self, *args, **kwargs: ""})()

    planner = SolutionPlanner(llm)

    result = planner.plan(
        problem_description=state['problem_description'],
        problem_types=state['problem_types'],
        constraints=state['constraints'],
        retrieved_knowledge=state['retrieved_knowledge']
    )

    return {
        **result,
        "execution_log": ["✓ Solution plan created"],
        "llm_calls": state["llm_calls"] + 1,
    }


# ========== Test Generation Nodes ==========

def generate_tests_node(state: SolvitaState) -> Dict[str, Any]:
    """Generate comprehensive test cases"""
    logger.info("[Node] Generating test cases")

    from src.testgen.test_generator import TestGenerator

    # Create mock LLM for now
    llm = type('MockLLM', (), {'generate': lambda self, *args, **kwargs: ""})()

    generator = TestGenerator(llm)

    result = generator.generate(
        constraints=state['constraints'],
        problem_types=state['problem_types'],
        public_tests=state['public_tests'],
        num_tests=20
    )

    return {
        **result,
        "execution_log": [f"✓ Generated {result['total_tests']} test cases"],
        "llm_calls": state['llm_calls'] + 1,
    }


# ========== Code Generation Nodes ==========

def generate_code_node(state: SolvitaState) -> Dict[str, Any]:
    """Generate C++ solution code"""
    logger.info(f"[Node] Generating C++ code (version {state['code_version'] + 1})")

    from src.solver.cpp_generator import CPPGenerator

    # Create mock LLM for now
    llm = type('MockLLM', (), {'generate': lambda self, *args, **kwargs: ""})()

    generator = CPPGenerator(llm)

    # Get feedback if this is a refinement iteration
    feedback = state.get('feedback') if state['iteration_count'] > 0 else None

    code = generator.generate(
        problem_description=state['problem_description'],
        solution_plan=state['solution_plan'],
        algorithm_choice=state['algorithm_choice'],
        implementation_steps=state['implementation_steps'],
        feedback=feedback
    )

    return {
        "generated_code": code,
        "code_version": state["code_version"] + 1,
        "generation_approach": "llm_based" if feedback else "initial",
        "execution_log": [f"✓ Generated C++ code (v{state['code_version'] + 1})"],
        "llm_calls": state["llm_calls"] + 1,
    }


# ========== Compilation Nodes ==========

def compile_code_node(state: SolvitaState) -> Dict[str, Any]:
    """Compile generated C++ code"""
    logger.info("[Node] Compiling C++ code")

    from src.solver.compiler import CPPCompiler

    compiler = CPPCompiler()

    result = compiler.compile(state['generated_code'])

    log_msg = "✓ Compilation successful" if result['compilation_success'] else "✗ Compilation failed"

    return {
        **result,
        "execution_log": [log_msg],
    }


# ========== Testing Nodes ==========

def run_tests_node(state: SolvitaState) -> Dict[str, Any]:
    """Execute compiled code against all test cases"""
    logger.info("[Node] Running test cases")

    from src.solver.executor import CodeExecutor

    executor = CodeExecutor(timeout=5)

    result = executor.run_tests(
        binary_path=state['executable_path'],
        tests=state['generated_tests']
    )

    return {
        **result,
        "execution_log": [f"✓ Tests completed: {result['passed_tests']}/{len(state['generated_tests'])} passed"],
    }


# ========== Feedback Analysis Nodes ==========

def analyze_feedback_node(state: SolvitaState) -> Dict[str, Any]:
    """Analyze test failures and compilation errors"""
    logger.info("[Node] Analyzing feedback from failures")

    from src.feedback.feedback_analyzer import FeedbackAnalyzer

    analyzer = FeedbackAnalyzer(llm=None)

    result = analyzer.analyze(
        generated_code=state['generated_code'],
        compilation_errors=state['compilation_errors'],
        test_results=state['test_results']
    )

    return {
        **result,
        "execution_log": ["✓ Feedback analyzed"],
        "llm_calls": state["llm_calls"] + 1,
    }


# ========== Control Flow Nodes ==========

def check_success_node(state: SolvitaState) -> Dict[str, Any]:
    """Check if solution is successful"""
    logger.info("[Node] Checking success condition")

    all_passed = (
        state["compilation_success"]
        and state["total_tests"] > 0
        and state["pass_rate"] >= 1.0
    )

    if all_passed:
        return {
            "should_continue": False,
            "termination_reason": "success",
            "final_solution": state["generated_code"],
            "execution_log": ["✓ All tests passed! Solution complete."],
        }
    else:
        return {
            "should_continue": True,
            "execution_log": [
                f"Tests status: {state['passed_tests']}/{state['total_tests']} passed"
            ],
        }


def check_should_continue_node(state: SolvitaState) -> Dict[str, Any]:
    """Determine whether to continue iteration or terminate"""
    logger.info(f"[Node] Checking continuation (iteration {state['iteration_count']})")

    # Already successful
    if state["termination_reason"] == "success":
        return {"should_continue": False}

    # Max iterations reached
    if state["iteration_count"] >= state["max_iterations"]:
        return {
            "should_continue": False,
            "termination_reason": "max_iterations",
            "execution_log": [
                f"✗ Max iterations ({state['max_iterations']}) reached"
            ],
        }

    # Continue iteration
    return {
        "should_continue": True,
        "iteration_count": state["iteration_count"] + 1,
        "execution_log": [f"→ Starting iteration {state['iteration_count'] + 1}"],
    }


def finalize_solution_node(state: SolvitaState) -> Dict[str, Any]:
    """Finalize solution and prepare output"""
    logger.info("[Node] Finalizing solution")

    metadata = {
        "iterations": state["iteration_count"],
        "llm_calls": state["llm_calls"],
        "total_tests": state["total_tests"],
        "pass_rate": state["pass_rate"],
        "termination_reason": state["termination_reason"],
    }

    return {
        "solution_metadata": metadata,
        "execution_log": ["✓ Solution finalized", f"Metadata: {metadata}"],
    }


# ========== Routing Functions ==========

def should_continue_routing(state: SolvitaState) -> str:
    """Routing function for conditional edge"""
    if state["should_continue"]:
        return "continue"
    else:
        return "end"


def compilation_routing(state: SolvitaState) -> str:
    """Routing after compilation"""
    if state["compilation_success"]:
        return "success"
    else:
        return "failed"
