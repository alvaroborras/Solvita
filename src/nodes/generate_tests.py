"""Generate Tests Node - Create test cases for the problem"""

from typing import Dict, Any
import json
from loguru import logger
from src.graph.state import SolvitaState, TestData
from src.llm import UnifiedLLMClient


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks

    Supports:
    - Pure JSON: {"key": "value"}
    - Markdown wrapped: ```json\n{"key": "value"}\n```
    - Generic code block: ```\n{"key": "value"}\n```
    """
    cleaned = response.strip()

    # Remove markdown code block markers
    if '```json' in cleaned:
        parts = cleaned.split('```json')
        if len(parts) > 1:
            cleaned = parts[1].split('```')[0].strip()
    elif '```' in cleaned:
        parts = cleaned.split('```')
        if len(parts) >= 3:
            cleaned = parts[1].strip()

    # Parse JSON
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response content: {cleaned[:200]}...")
        raise


def generate_tests_node(state: SolvitaState) -> Dict[str, Any]:
    """
    Generate test cases based on problem and public tests

    Generates:
    - Edge cases (boundary values)
    - Corner cases (special scenarios)
    - Random cases (within constraints)
    """
    logger.info("[Node] Generating test cases")

    # Initialize LLM
    llm = UnifiedLLMClient(state['config'])

    problem_desc = state['problem'].get('description', '')
    public_tests = state['problem'].get('public_tests', [])
    constraints = state['problem'].get('constraints', {})

    # Build test generation prompt
    prompt = f"""Generate comprehensive test cases for this competitive programming problem.

Problem Description:
{problem_desc}

Constraints: {constraints}

Public Tests (for reference):
{json.dumps(public_tests, indent=2)}

Please generate additional test cases in JSON format to thoroughly validate solutions:

{{
  "test_cases": [
    {{
      "input": "test input data (match problem's input format)",
      "expected_output": "expected output",
      "type": "edge|corner|random",
      "description": "brief description of what this tests"
    }}
  ]
}}

Requirements:
1. Edge cases: Test boundary values (min/max constraints, empty input, single element)
2. Corner cases: Test special scenarios (duplicates, all same values, negative numbers)
3. Random cases: Test typical valid inputs

Generate 5-10 additional test cases. Ensure inputs match the problem's format exactly.

Return ONLY the JSON object, no additional text."""

    # Get test generation response
    response = llm.generate(prompt)

    # Start with public tests
    generated_tests = []
    for pt in public_tests:
        generated_tests.append({
            'input': pt.get('input', ''),
            'expected_output': pt.get('output', ''),
            'type': 'public',
            'description': 'Public test case'
        })

    # Parse and add LLM-generated tests
    try:
        test_data = parse_json_response(response)
        additional_tests = test_data.get('test_cases', [])

        # Validate and add each test
        for test in additional_tests:
            if 'input' in test and 'expected_output' in test:
                generated_tests.append({
                    'input': test.get('input', ''),
                    'expected_output': test.get('expected_output', ''),
                    'type': test.get('type', 'generated'),
                    'description': test.get('description', '')
                })

        logger.info(f"Added {len(additional_tests)} LLM-generated tests")

    except json.JSONDecodeError:
        logger.warning("Failed to parse test generation response, using only public tests")

    # Count test types
    test_counts = {
        'public': sum(1 for t in generated_tests if t['type'] == 'public'),
        'edge': sum(1 for t in generated_tests if t['type'] == 'edge'),
        'corner': sum(1 for t in generated_tests if t['type'] == 'corner'),
        'random': sum(1 for t in generated_tests if t['type'] == 'random'),
        'generated': sum(1 for t in generated_tests if t['type'] == 'generated'),
    }

    tests = TestData(
        generated_tests=generated_tests,
        total_tests=len(generated_tests),
        test_results=[],
        passed_tests=0,
        pass_rate=0.0,
    )

    return {
        "tests": tests,
        "execution_log": [
            f"Generated {len(generated_tests)} test cases",
            f"  Public: {test_counts['public']}, Edge: {test_counts['edge']}, "
            f"Corner: {test_counts['corner']}, Random: {test_counts['random']}, "
            f"Other: {test_counts['generated']}"
        ],
        "llm_calls": 1,
    }

