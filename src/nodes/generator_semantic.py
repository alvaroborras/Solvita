import json
from typing import Dict, Any, List, Optional
from loguru import logger

from src.llm import UnifiedLLMClient
from src.utils.json_utils import parse_json_response

def build_semantic_generator_prompt(
    problem_desc: str, 
    constraints: Dict[str, Any], 
    analyst_report: Dict[str, Any],
    memory_advice: str = ""
) -> str:
    """
    Constructs the prompt instructing the LLM to write a targeted C++ Semantic Test Generator.
    """
    constraints_json = json.dumps(constraints, indent=2)
    report_json = json.dumps(analyst_report, indent=2)
    
    advice_section = ""
    if memory_advice:
        advice_section = f"\n=== HACKER STRATEGY ADVICE ===\n{memory_advice}\n=============================\n"

    return f"""You are the Semantic Generator, a specialized C++ coder for an adversarial Hacker System.
Your job is to write a standalone C++ program that generates a single, highly-targeted test case designed to trigger the specific vulnerability described by the Code Analyst.

PROBLEM DESCRIPTION:
{problem_desc}
{advice_section}
CONSTRAINTS (The output of your C++ generator MUST satisfy ALL of these):
{constraints_json}

VULNERABILITY REPORT (from Code Analyst):
{report_json}

INSTRUCTIONS FOR C++ GENERATOR:
1. Write a complete, compilable C++17 program (`int main() {{...}}`).
2. The program must print EXACTLY ONE valid test case to standard output (`std::cout`).
3. Focus on producing the input data structures matching the `input_hypothesis` in the report.
4. DO NOT use uninitialized variables or undefined behavior in your generator.
5. If you need randomness, you MAY use `<random>` (`std::mt19937`), but since this is the Semantic Generator, deterministic construction of the edge case is preferred when possible.

CRITICAL FORMATTING RULES:
1. Return ONLY the C++ code.
2. DO NOT wrap the code in markdown blocks (e.g., ```cpp ... ```).
3. The very first line should be `#include <...>` or similar valid C++.

Write the C++ generator code now:
"""

def generate_semantic_test_program(
    state: Dict[str, Any], 
    llm: UnifiedLLMClient, 
    analyst_report: Dict[str, Any]
) -> str:
    """
    Invokes the LLM to generate the Semantic C++ Test Generator.
    """
    logger.info(f"[Semantic Generator] Targeting bug class '{analyst_report.get('bug_class')}'...")
    
    problem_desc = state.get("problem", {}).get("description", "")
    constraints = state.get("problem", {}).get("constraints", {})
    
    # We do NOT pass the target code here, to force the LLM to focus purely on 
    # the semantic data structural generation based on the Analyst's insight.
    prompt = build_semantic_generator_prompt(problem_desc, constraints, analyst_report, memory_advice="")
    
    cpp_source = llm.generate(prompt)
    
    # Clean up any potential markdown adherence failure
    from src.utils.cpp_execution import sanitize_cpp
    try:
        clean_cpp = sanitize_cpp(cpp_source)
    except Exception as e:
        logger.warning(f"[Semantic Generator] LLM produced invalid/dangerous format: {e}")
        # Return fallback empty/failing generator if parsing fails completely, 
        # relying on Router to retry or downgrade
        return "int main() { return 1; }"
        
    return clean_cpp
