import json
from typing import Dict, Any
from loguru import logger

from src.llm import UnifiedLLMClient

def build_stress_generator_prompt(
    problem_desc: str, 
    constraints: Dict[str, Any], 
) -> str:
    """
    Constructs the prompt instructing the LLM to write a high-throughput C++ Fuzzer.
    """
    constraints_json = json.dumps(constraints, indent=2)

    return f"""You are the Stress Test Generator, a specialized C++ coder for an adversarial Hacker System.
Your job is to write a standalone C++ program (`int main()`) that acts as a high-throughput Fuzzer.

PROBLEM DESCRIPTION:
{problem_desc}

CONSTRAINTS (The output of your C++ fuzzer MUST strictly satisfy these boundaries):
{constraints_json}

INSTRUCTIONS FOR C++ FUZZER:
1. Write a complete, compilable C++17 program.
2. The program must print EXACTLY ONE valid test case to standard output, but this test case should be as LARGE and COMPLEX as the constraints allow.
3. You MUST use `<random>` and `std::mt19937_64` initialized with a random device or fixed seed.
4. Scale up the generation loop to approach the maximum `N`, `M`, or `K` allowed.
5. Emphasize boundary values (e.g. generating values alternating between min and max allowed).
6. Optimize the generator for speed using `\\n` instead of `std::endl` and fast I/O (`std::ios_base::sync_with_stdio(false);`).

CRITICAL FORMATTING RULES:
1. Return ONLY the C++ code.
2. DO NOT wrap the code in markdown blocks (e.g., ```cpp ... ```).
3. The very first line should be `#include <...>` or similar valid C++.

Write the C++ Stress Test Generator code now:
"""

def generate_stress_test_program(
    state: Dict[str, Any], 
    llm: UnifiedLLMClient, 
) -> str:
    """
    Invokes the LLM to generate the Stress C++ Fuzzer.
    """
    logger.info("[Stress Generator] Generating boundary/randomized fallback Fuzzer...")
    
    problem_desc = state.get("problem", {}).get("description", "")
    constraints = state.get("problem", {}).get("constraints", {})
    
    prompt = build_stress_generator_prompt(problem_desc, constraints)
    cpp_source = llm.generate(prompt)
    
    from src.utils.cpp_execution import sanitize_cpp
    try:
        clean_cpp = sanitize_cpp(cpp_source)
    except Exception as e:
        logger.warning(f"[Stress Generator] LLM produced invalid/dangerous format: {e}")
        return "int main() { return 1; }"
        
    return clean_cpp
