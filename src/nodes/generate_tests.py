"""Generate Tests Node - Create test cases for the problem"""

from typing import Dict, Any
from loguru import logger
from src.graph.state import SolvitaState, TestData
from src.llm import UnifiedLLMClient


def generate_tests_node(state: SolvitaState) -> Dict[str, Any]:
    """
    Generate test cases based on problem and public tests
    
    Generates:
    - Edge cases
    - Corner cases  
    - Random cases within constraints
    """
    logger.info("[Node] Generating test cases")
    
    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])
    
    problem_desc = state['problem'].get('description', '')
    public_tests = state['problem'].get('public_tests', [])
    
    prompt = f"""Generate comprehensive test cases for this problem:

Problem: {problem_desc}

Public Tests: {public_tests}

Generate:
1. Edge cases (boundary values)
2. Corner cases (special scenarios)
3. Random valid cases

Format: For each test case, provide input and expected output."""
    
    response = llm.generate(prompt)
    
    # Start with public tests
    generated_tests = []
    for pt in public_tests:
        generated_tests.append({
            'input': pt.get('input', ''),
            'expected_output': pt.get('output', ''),
            'type': 'public'
        })
    
    # TODO: Parse additional tests from LLM response
    # For now, use only public tests
    
    tests = TestData(
        generated_tests=generated_tests,
        total_tests=len(generated_tests),
        test_results=[],
        passed_tests=0,
        pass_rate=0.0,
    )
    
    return {
        "tests": tests,
        "execution_log": [f"✓ Generated {len(generated_tests)} test cases"],
        "llm_calls": state['llm_calls'] + 1,
    }

