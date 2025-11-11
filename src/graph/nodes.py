"""LangGraph Node Implementations - Connected to Real Modules

All nodes now call actual module implementations.
"""

from typing import Dict, Any
from src.graph.state import SolvitaState
from loguru import logger


# ========== Problem Understanding Nodes ==========

def parse_problem_node(state: SolvitaState) -> Dict[str, Any]:
    """Parse raw problem input into structured format"""
    logger.info(f"[Node] Parsing problem (iteration {state['iteration']})")

    from src.parser.problem_parser import ProblemParser
    from src.graph.state import ProblemData

    parser = ProblemParser(llm=None)
    parsed = parser.parse(state['raw_problem'])

    # Organize parsed data into ProblemData object
    problem = ProblemData(
        description=parsed.get("problem_description", ""),
        types=parsed.get("problem_types", []),
        constraints=parsed.get("constraints", {}),
        public_tests=parsed.get("public_tests", []),
        retrieved_knowledge=state['problem'].get('retrieved_knowledge', []),
    )

    return {
        "problem": problem,
        "execution_log": ["✓ Problem parsed successfully"],
    }


# ========== Knowledge Retrieval Nodes ==========

def retrieve_knowledge_node(state: SolvitaState) -> Dict[str, Any]:
    """Retrieve relevant knowledge from knowledge base"""
    logger.info("[Node] Retrieving relevant knowledge")

    # TODO: Implement actual knowledge retrieval when Neo4j/Vector DB are set up
    # Currently returns empty lists as placeholder

    return {
        "problem": {
            # Core retrieved data
            "retrieved_knowledge": [],

            # TODO: Future fields for enhanced knowledge retrieval
            # These will be populated when Neo4j/Vector DB integration is complete
            "relevant_algorithms": [],      # e.g., ["DP", "Two Pointers", "BFS"]
            "relevant_data_structures": [], # e.g., ["HashMap", "Stack", "Heap"]
            "similar_problems": [],         # e.g., [{"id": 123, "solution": "..."}]
        },
        "execution_log": ["Knowledge retrieval skipped (not implemented)"],
    }


# ========== Planning Nodes ==========

def plan_solution_node(state: SolvitaState) -> Dict[str, Any]:
    """Generate high-level solution plan"""
    logger.info("[Node] Planning solution approach")

    from src.planner.solution_planner import SolutionPlanner
    from src.llm.model_factory import ModelFactory
    from src.graph.state import PlanData

    # Get LLM from config or use mock
    try:
        llm = ModelFactory.create_from_config(state['config'])
    except Exception as e:
        logger.warning(f"Failed to create LLM: {e}, using mock LLM")
        llm = ModelFactory.create_mock()

    planner = SolutionPlanner(llm)

    result = planner.plan(
        problem_description=state['problem'].get('description', ''),
        problem_types=state['problem'].get('types', []),
        constraints=state['problem'].get('constraints', {}),
        retrieved_knowledge=state['problem'].get('retrieved_knowledge', [])
    )

    # Organize planning results into PlanData object
    plan = PlanData(
        solution_plan=result.get('solution_plan', {}),
        algorithm_choice=result.get('algorithm_choice', ''),
        implementation_steps=result.get('implementation_steps', []),
    )

    return {
        "plan": plan,
        "execution_log": ["✓ Solution plan created"],
        "llm_calls": state["llm_calls"] + 1,
    }


# ========== Test Generation Nodes ==========

def generate_tests_node(state: SolvitaState) -> Dict[str, Any]:
    """Generate comprehensive test cases"""
    logger.info("[Node] Generating test cases")

    from src.testgen.test_generator import TestGenerator
    from src.llm.model_factory import ModelFactory
    from src.graph.state import TestData

    # Create LLM instance
    try:
        llm = ModelFactory.create_from_config(state['config'])
    except Exception as e:
        logger.warning(f"Failed to create LLM: {e}, using mock LLM")
        llm = ModelFactory.create_mock()

    generator = TestGenerator(llm)

    result = generator.generate(
        constraints=state['problem'].get('constraints', {}),
        problem_types=state['problem'].get('types', []),
        public_tests=state['problem'].get('public_tests', []),
        num_tests=20
    )

    # Organize test generation results into TestData object
    tests = TestData(
        generated_tests=result.get('generated_tests', []),
        total_tests=result.get('total_tests', 0),
        test_results=[],  # Will be populated by run_tests_node
        passed_tests=0,   # Will be populated by run_tests_node
        pass_rate=0.0,    # Will be populated by run_tests_node
    )

    return {
        "tests": tests,
        "execution_log": [f"✓ Generated {result['total_tests']} test cases"],
        "llm_calls": state['llm_calls'] + 1,
    }


# ========== Code Generation Nodes ==========

def generate_code_node(state: SolvitaState) -> Dict[str, Any]:
    """Generate C++ solution code"""
    logger.info(f"[Node] Generating C++ code (version {state['solution'].get('version', 0) + 1})")

    from src.solver.cpp_generator import CPPGenerator
    from src.llm.model_factory import ModelFactory
    from src.graph.state import SolutionData

    # Create LLM instance
    try:
        llm = ModelFactory.create_from_config(state['config'])
    except Exception as e:
        logger.warning(f"Failed to create LLM: {e}, using mock LLM")
        llm = ModelFactory.create_mock()

    generator = CPPGenerator(llm)

    # Get feedback if this is a refinement iteration
    feedback = state['feedback'].get('feedback') if state['iteration'] > 0 else None

    code = generator.generate(
        problem_description=state['problem'].get('description', ''),
        solution_plan=state['plan'].get('solution_plan', {}),
        algorithm_choice=state['plan'].get('algorithm_choice', ''),
        implementation_steps=state['plan'].get('implementation_steps', []),
        feedback=feedback
    )

    # Organize code generation results into SolutionData object
    solution = SolutionData(
        code=code,
        version=state['solution'].get('version', 0) + 1,
        compilation_success=False,           # Will be updated by compile_code_node
        compilation_errors=[],                # Will be updated by compile_code_node
        executable_path=None,                 # Will be updated by compile_code_node
    )

    return {
        "solution": solution,
        "execution_log": [f"✓ Generated C++ code (v{state['solution'].get('version', 0) + 1})"],
        "llm_calls": state["llm_calls"] + 1,
    }


# ========== Compilation Nodes ==========

def compile_code_node(state: SolvitaState) -> Dict[str, Any]:
    """Compile generated C++ code"""
    logger.info("[Node] Compiling C++ code")

    from src.solver.compiler import CPPCompiler
    from src.graph.state import SolutionData

    compiler = CPPCompiler()

    result = compiler.compile(state['solution'].get('code', ''))

    log_msg = "✓ Compilation successful" if result.get('compilation_success', False) else "✗ Compilation failed"

    # Organize compilation results into SolutionData object
    solution = SolutionData(
        code=state['solution'].get('code', ''),
        version=state['solution'].get('version', 0),
        compilation_success=result.get('compilation_success', False),
        compilation_errors=result.get('compilation_errors', []),
        executable_path=result.get('executable_path', None),
    )

    return {
        "solution": solution,
        "execution_log": [log_msg],
    }


# ========== Testing Nodes ==========

def run_tests_node(state: SolvitaState) -> Dict[str, Any]:
    """Execute compiled code against all test cases"""
    logger.info("[Node] Running test cases")

    from src.solver.executor import CodeExecutor
    from src.graph.state import TestData

    executor = CodeExecutor(timeout=5)

    result = executor.run_tests(
        binary_path=state['solution'].get('executable_path'),
        tests=state['tests'].get('generated_tests', [])
    )

    # Organize test execution results into TestData object
    tests = TestData(
        generated_tests=state['tests'].get('generated_tests', []),
        total_tests=state['tests'].get('total_tests', 0),
        test_results=result.get('test_results', []),
        passed_tests=result.get('passed_tests', 0),
        pass_rate=result.get('pass_rate', 0.0),
    )

    return {
        "tests": tests,
        "execution_log": [f"✓ Tests completed: {result.get('passed_tests', 0)}/{state['tests'].get('total_tests', 0)} passed"],
    }


# ========== Feedback Analysis Nodes ==========

def analyze_feedback_node(state: SolvitaState) -> Dict[str, Any]:
    """Analyze test failures and compilation errors"""
    logger.info("[Node] Analyzing feedback from failures")

    from src.feedback.feedback_analyzer import FeedbackAnalyzer
    from src.graph.state import FeedbackData

    analyzer = FeedbackAnalyzer(llm=None)

    result = analyzer.analyze(
        generated_code=state['solution'].get('code', ''),
        compilation_errors=state['solution'].get('compilation_errors', []),
        test_results=state['tests'].get('test_results', [])
    )

    # Organize feedback results into FeedbackData object
    feedback = FeedbackData(
        feedback=result.get('feedback', {}),
        suggested_fixes=result.get('suggested_fixes', []),
    )

    return {
        "feedback": feedback,
        "execution_log": ["✓ Feedback analyzed"],
        "llm_calls": state["llm_calls"] + 1,
    }


# ========== Control Flow Nodes ==========

def unified_check_node(state: SolvitaState) -> Dict[str, Any]:
    """
    Unified check node that determines solution status and iteration control.

    Combines the logic of check_success_node and check_should_continue_node
    into a single node for clarity and efficiency.
    """
    logger.info(f"[Node] Unified check (iteration {state['iteration']})")

    # Check 1: Are all tests passing?
    all_passed = (
        state['solution'].get('compilation_success', False)
        and state['tests'].get('total_tests', 0) > 0
        and state['tests'].get('pass_rate', 0.0) >= 1.0
    )

    if all_passed:
        return {
            "status": "success",
            "execution_log": ["✓ All tests passed! Solution complete."],
        }

    # Check 2: Have we reached max iterations?
    if state["iteration"] >= state["max_iterations"]:
        return {
            "status": "max_iterations",
            "execution_log": [
                f"✗ Max iterations ({state['max_iterations']}) reached"
            ],
        }

    # Check 3: Continue iteration
    return {
        "iteration": state["iteration"] + 1,
        "execution_log": [
            f"Tests status: {state['tests'].get('passed_tests', 0)}/{state['tests'].get('total_tests', 0)} passed",
            f"→ Starting iteration {state['iteration'] + 1}",
        ],
    }


def finalize_solution_node(state: SolvitaState) -> Dict[str, Any]:
    """Finalize solution and prepare output"""
    logger.info("[Node] Finalizing solution")

    metadata = {
        "iterations": state["iteration"],
        "llm_calls": state["llm_calls"],
        "total_tests": state['tests'].get('total_tests', 0),
        "pass_rate": state['tests'].get('pass_rate', 0.0),
        "status": state["status"],
    }

    return {
        "execution_log": ["✓ Solution finalized", f"Metadata: {metadata}"],
    }


# ========== Routing Functions ==========

def status_routing(state: SolvitaState) -> str:
    """Routing function based on status"""
    status = state.get("status", "pending")

    if status == "success":
        return "end"
    elif status == "max_iterations":
        return "end"
    else:
        return "continue"


def compilation_routing(state: SolvitaState) -> str:
    """Routing after compilation"""
    if state['solution'].get('compilation_success', False):
        return "success"
    else:
        return "failed"
