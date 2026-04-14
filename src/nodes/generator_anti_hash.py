import json
from typing import Dict, Any
from loguru import logger

from src.llm import UnifiedLLMClient
from src.nodes.generator_common import render_input_validity_constraints
from src.utils.prompt_templates import render_template

def build_anti_hash_generator_prompt(
    problem_desc: str, 
    constraints_text: str, 
    analyst_report: Dict[str, Any]
) -> str:
    """
    Constructs the prompt instructing the LLM to write a Hash Collision C++ Generator.
    """
    report_json = json.dumps(analyst_report, indent=2)

    return render_template(
        "hacker_generators.anti_hash.generator",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_TEXT=constraints_text,
        REPORT_JSON=report_json,
    )

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
    constraints_text = render_input_validity_constraints(state)
    
    prompt = build_anti_hash_generator_prompt(problem_desc, constraints_text, analyst_report)
    cpp_source = llm.generate(prompt)
    
    from src.utils.cpp_execution import sanitize_cpp
    try:
        clean_cpp = sanitize_cpp(cpp_source)
    except Exception as e:
        logger.warning(f"[Anti-Hash Generator] LLM produced invalid/dangerous format: {e}")
        return "int main() { return 1; }"
        
    return clean_cpp
