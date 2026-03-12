import json
from typing import Dict, Any
from loguru import logger

from src.llm import UnifiedLLMClient

def build_anti_hash_generator_prompt(
    problem_desc: str, 
    constraints: Dict[str, Any], 
    analyst_report: Dict[str, Any]
) -> str:
    """
    Constructs the prompt instructing the LLM to write a Hash Collision C++ Generator.
    """
    constraints_json = json.dumps(constraints, indent=2)
    report_json = json.dumps(analyst_report, indent=2)

    return f"""You are the Anti-Hash Generator, the cryptography/math specialist for an adversarial Hacker System.
Your job is to read the Code Analyst's report identifying a polynomial rolling hash susceptibility, and write a standalone C++ program to generate colliding strings.

PROBLEM DESCRIPTION:
{problem_desc}

CONSTRAINTS (Output MUST SATISFY ALL string/length constraints):
{constraints_json}

VULNERABILITY REPORT (from Code Analyst):
{report_json}

INSTRUCTIONS FOR C++ GENERATOR:
1. Write a complete, compilable C++17 program (`int main()`).
2. Implement a collision derivation algorithm (e.g., Thue-Morse sequence, Birthday attack, or specific moduli exploitation) matching the `input_hypothesis`.
3. Output EXACTLY the string(s) needed to trigger the collision to standard out.
4. Keep the target constraints in mind. If max length is `N=10^5`, the collision strings must not exceed this length.

CRITICAL FORMATTING RULES:
1. Return ONLY the C++ code.
2. DO NOT wrap the code in markdown blocks (e.g., ```cpp ... ```).
3. The very first line should be `#include <...>` or similar valid C++.

Write the C++ Collision Generator code now:
"""

def generate_anti_hash_test_program(
    state: Dict[str, Any], 
    llm: UnifiedLLMClient, 
    analyst_report: Dict[str, Any]
) -> str:
    """
    Invokes the LLM to generate the Anti-Hash Collision C++ Generator.
    """
    logger.info("[Anti-Hash Generator] Forging mathematical collision sequence...")
    
    problem_desc = state.get("problem", {}).get("description", "")
    constraints = state.get("problem", {}).get("constraints", {})
    
    prompt = build_anti_hash_generator_prompt(problem_desc, constraints, analyst_report)
    cpp_source = llm.generate(prompt)
    
    from src.utils.cpp_execution import sanitize_cpp
    try:
        clean_cpp = sanitize_cpp(cpp_source)
    except Exception as e:
        logger.warning(f"[Anti-Hash Generator] LLM produced invalid/dangerous format: {e}")
        return "int main() { return 1; }"
        
    return clean_cpp
