"""Bootstrap a trusted lightweight test suite before full test generation."""

from collections import Counter
import json
from typing import Any, Dict, List, TYPE_CHECKING

from src.utils.test_seed_cases import build_local_certified_tests

if TYPE_CHECKING:
    from src.graph.state import SolvitaState


def _build_problem_desc(state: "SolvitaState") -> str:
    canonical = (state.get("problem") or {}).get("canonical", {})
    if canonical:
        return (
            f"Objective: {canonical.get('objective', '')}\n"
            f"Inputs: {json.dumps(canonical.get('inputs', {}), indent=2)}\n"
            f"Outputs: {json.dumps(canonical.get('outputs', {}), indent=2)}\n"
            f"Constraints: {json.dumps(canonical.get('constraints', {}), indent=2)}"
        )
    return (state.get("problem") or {}).get("description", "")


def _build_failure_bank_tests(counterexamples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tests: List[Dict[str, Any]] = []
    for item in counterexamples:
        expected_output = item.get("expected_output", item.get("output_text", ""))
        tests.append(
            {
                "input": item.get("input_text", ""),
                "expected_output": expected_output,
                "type": "failure_bank",
                "description": (
                    f"Failure-bank counterexample ({item.get('failure_type', 'unknown')})"
                    if item.get("failure_type")
                    else "Failure-bank counterexample"
                ),
                "trust_tier": "trusted",
            }
        )
    return tests


def bootstrap_tests_node(state: "SolvitaState") -> Dict[str, Any]:
    public_tests = (state.get("problem") or {}).get("public_tests", [])
    problem_desc = _build_problem_desc(state)
    local_certified_tests = build_local_certified_tests(problem_desc)
    counterexamples = (state.get("failure_bank_context") or {}).get("retrieved_counterexamples", [])

    generated_tests: List[Dict[str, Any]] = []
    for test in public_tests:
        generated_tests.append(
            {
                "input": test.get("input", ""),
                "expected_output": test.get("output", ""),
                "type": "public",
                "description": "Public test case",
                "trust_tier": "trusted",
            }
        )

    for test in local_certified_tests:
        generated_tests.append(
            {
                "input": test.get("input", ""),
                "expected_output": test.get("output", ""),
                "type": test.get("type", "edge"),
                "description": test.get("description", "Local exact certification case"),
                "trust_tier": "trusted",
            }
        )

    generated_tests.extend(_build_failure_bank_tests(counterexamples))

    trust_counts = Counter(test.get("trust_tier", "trusted") for test in generated_tests)
    execution_log = [f"Bootstrapped {len(generated_tests)} trusted test cases"]

    return {
        "tests": {
            "generated_tests": generated_tests,
            "total_tests": len(generated_tests),
            "test_results": [],
            "passed_tests": 0,
            "pass_rate": 0.0,
            "pending_execution": False,
            "ready": True,
            "full_testgen_completed": False,
            "trust_tiers": dict(trust_counts),
        },
        "execution_log": execution_log,
    }
