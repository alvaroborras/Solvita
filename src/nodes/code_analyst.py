import json
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

from src.llm import UnifiedLLMClient
from src.utils.python_execution import run_python
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits

def parse_code_analyst_response(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parses the LLM response to determine if it is a tool call or the final report.
    Strips markdown code blocks (`json`) if present.
    Returns:
        (response_type, parsed_dict)
        where response_type is either "tool_call", "final_report", or "error".
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return "error", {"message": f"Invalid JSON format: {str(e)}\nPlease output valid JSON."}
        
    # Heuristic to separate tool calls from the final report
    if "tool" in data and "parameters" in data:
        tool_name = data.get("tool")
        if tool_name not in ("run_python", "run_cpp"):
            return "error", {"message": f"Forbidden or unknown tool '{tool_name}'. Allowed tools are: run_python, run_cpp."}
        return "tool_call", data
        
    if "bug_class" in data and "suggested_route" in data:
        # Validate schema
        required_keys = {"bug_class", "confidence", "evidence", "suggested_route", "input_hypothesis"}
        missing = required_keys - set(data.keys())
        if missing:
            return "error", {"message": f"Final report is missing required keys: {', '.join(missing)}"}
            
        # Value Enum validations
        valid_bug_classes = {"overflow", "hash_collision", "index_oob", "tle", "logic_branch", "unknown"}
        if data["bug_class"] not in valid_bug_classes:
            return "error", {"message": f"Invalid bug_class: {data['bug_class']}. Must be one of {valid_bug_classes}"}
            
        valid_confidence = {"high", "medium", "low"}
        if data["confidence"] not in valid_confidence:
            return "error", {"message": f"Invalid confidence: {data['confidence']}. Must be one of {valid_confidence}"}
            
        valid_routes = {"anti_hash", "semantic", "stress"}
        if data["suggested_route"] not in valid_routes:
            return "error", {"message": f"Invalid suggested_route: {data['suggested_route']}. Must be one of {valid_routes}"}
            
        if not isinstance(data["evidence"], list) or not isinstance(data["input_hypothesis"], list):
            return "error", {"message": "evidence and input_hypothesis must be lists of strings"}
            
        return "final_report", data
        
    return "error", {"message": "Unrecognized JSON structure. Return either a Tool Call or the Final Vulnerability Report."}


def execute_tool(tool_name: str, parameters: Dict[str, Any]) -> str:
    """Executes the requested tool and returns the output as a string."""
    if tool_name == "run_python":
        script_code = parameters.get("script_code", "")
        if not script_code:
            return "Error: Missing 'script_code' parameter."
        ret, out, err = run_python(script_code)
        if ret == 124:
            return f"Timeout! Execution exceeded limits.\n{err}"
        elif ret != 0:
            return f"Execution failed (Code {ret}):\n{err}"
        return f"Execution successful:\n{out}"
        
    elif tool_name == "run_cpp":
        cpp_code = parameters.get("cpp_code", "")
        if not cpp_code:
            return "Error: Missing 'cpp_code' parameter."
            
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = Path(tmpdir) / "probe.cpp"
            exe_path = Path(tmpdir) / "probe.exe"
            src_path.write_text(cpp_code, encoding="utf-8")
            
            # Use hacker compile limits
            compiled, comp_out = compile_cpp(src_path, exe_path, limits=ExecutionLimits.hacker_compile())
            if not compiled:
                return f"C++ Compilation failed:\n{comp_out}"
                
            ret, out, err = run_program(exe_path, limits=ExecutionLimits.hacker_run())
            if ret == 124:
                return f"Timeout! Execution exceeded {ExecutionLimits.hacker_run().wall_seconds}s limit.\n{err}"
            elif ret != 0:
                return f"Runtime Error (Code {ret}):\n{err}"
            return f"Execution successful:\n{out}"
    
    return f"Error: Executor for '{tool_name}' not implemented."


def build_analyst_prompt(problem_desc: str, constraints: Dict[str, Any], target_code: str, history: List[str], memory_advice: str = "") -> str:
    constraints_json = json.dumps(constraints, indent=2)
    history_text = "\n\n".join(history) if history else "No actions taken yet."
    advice_section = ""
    if memory_advice:
        advice_section = f"\nHACKER STRATEGY ADVICE:\n{memory_advice}\n"
    
    return f"""You are the Code Analyst, the strategy planner for an adversarial Hacker System.
Your goal is to find bugs, logic flaws, or vulnerabilities (WA, TLE, RE, MLE) in the provided C++ target code.

PROBLEM DESCRIPTION:
{problem_desc}

CONSTRAINTS:
{constraints_json}

TARGET SOLUTION CODE (May contain bugs):
```cpp
{target_code}
```
{advice_section}

AVAILABLE TOOLS:
You can verify your hypothesis by writing short probe codes. Do not guess blindly if you can test it!
Tool 1: `run_python`
Use this to perform precise mathematical calculations (e.g., combinations, large numbers) to check constraints and overflows.
Inputs: {{"tool": "run_python", "parameters": {{"script_code": "..."}}}}

Tool 2: `run_cpp`
Use this to compile and execute small C++ snippets to test specific runtime behaviors or replicate target logic.
Inputs: {{"tool": "run_cpp", "parameters": {{"cpp_code": "..."}}}}

RESPONSE FORMAT:
You must return a valid JSON object. You have two choices:
Choice A: Call a tool to gather information.
{{
    "tool": "run_python",
    "parameters": {{"script_code": "import math\\nprint(math.comb(100, 50))"}}
}}

Choice B: Submit the Final Vulnerability Report (if you are confident).
{{
    "bug_class": "overflow|hash_collision|index_oob|tle|logic_branch|unknown",
    "confidence": "high|medium|low",
    "evidence": ["e.g. math.comb(100,50) overflows 2^63"],
    "suggested_route": "anti_hash|semantic|stress",
    "input_hypothesis": ["large_n", "degenerate_tree", "collision_string"]
}}
Note on routes: `anti_hash` if polynomial hash is used. `semantic` for most logical bugs. `stress` ONLY if entirely clueless.

HISTORY OF YOUR ACTIONS & RESULTS:
{history_text}

Analyze the code, call tools if needed to verify, and output valid JSON.
"""


def build_json_repair_prompt(
    previous_response: str,
    problem_desc: str,
    constraints: Dict[str, Any],
    target_code: str,
    memory_advice: str = "",
) -> str:
    constraints_json = json.dumps(constraints, indent=2)
    advice_section = ""
    if memory_advice:
        advice_section = f"\nHACKER STRATEGY ADVICE:\n{memory_advice}\n"

    return f"""Your previous reply was not valid JSON for the Code Analyst protocol.

Rewrite the same intent as ONE valid JSON object.
Allowed outputs:
1. A tool call:
{{
  "tool": "run_python|run_cpp",
  "parameters": {{...}}
}}

2. A final report:
{{
  "bug_class": "overflow|hash_collision|index_oob|tle|logic_branch|unknown",
  "confidence": "high|medium|low",
  "evidence": ["..."],
  "suggested_route": "anti_hash|semantic|stress",
  "input_hypothesis": ["..."]
}}

Previous reply:
{previous_response}

PROBLEM DESCRIPTION:
{problem_desc}

CONSTRAINTS:
{constraints_json}

TARGET SOLUTION CODE:
```cpp
{target_code}
```
{advice_section}

Return valid JSON only. Do not add any explanation, markdown, or commentary.
"""


def build_force_tool_prompt(
    problem_desc: str,
    constraints: Dict[str, Any],
    target_code: str,
    history: List[str],
    weak_report: Dict[str, Any],
    memory_advice: str = "",
) -> str:
    constraints_json = json.dumps(constraints, indent=2)
    history_text = "\n\n".join(history) if history else "No actions taken yet."
    weak_report_json = json.dumps(weak_report, indent=2)
    advice_section = ""
    if memory_advice:
        advice_section = f"\nHACKER STRATEGY ADVICE:\n{memory_advice}\n"

    return f"""Your current vulnerability report is too weak to submit as a final answer.

You must call exactly one tool before you can submit a final report.
Do not submit a final report yet.
Return ONLY a tool call JSON object in one of these forms:
{{
  "tool": "run_python",
  "parameters": {{"script_code": "..."}}
}}
or
{{
  "tool": "run_cpp",
  "parameters": {{"cpp_code": "..."}}
}}

PROBLEM DESCRIPTION:
{problem_desc}

CONSTRAINTS:
{constraints_json}

TARGET SOLUTION CODE:
```cpp
{target_code}
```
{advice_section}
PREVIOUS WEAK REPORT:
{weak_report_json}

HISTORY OF ACTIONS:
{history_text}

Call one tool that will increase confidence in the bug class or input hypothesis.
"""


def should_force_tool_validation(report: Dict[str, Any], has_tool_evidence: bool) -> bool:
    if has_tool_evidence:
        return False
    return report.get("bug_class") == "unknown" or report.get("confidence") == "low"

def run_code_analyst(state: Dict[str, Any], llm: UnifiedLLMClient, max_rounds: int = 5, memory_advice: str = "") -> Dict[str, Any]:
    """
    Executes the Code Analyst loop (up to `max_rounds` times).
    Returns the parsed Vulnerability Report.
    """
    logger.info("[Code Analyst] Starting investigation...")
    
    problem_desc = state.get("problem", {}).get("description", "")
    constraints = state.get("problem", {}).get("constraints", {})
    target_code = state.get("solution", {}).get("code", "")
    
    history = []
    has_tool_evidence = False
    round_num = 1

    while round_num <= max_rounds:
        prompt = build_analyst_prompt(problem_desc, constraints, target_code, history, memory_advice=memory_advice)
        response_text = llm.generate(prompt)
        
        logger.debug(f"[Code Analyst] Round {round_num} raw response:\n{response_text[:300]}...")
        while True:
            res_type, parsed_data = parse_code_analyst_response(response_text)

            if res_type == "final_report":
                if should_force_tool_validation(parsed_data, has_tool_evidence):
                    logger.info("[Code Analyst] Weak final report detected. Forcing one tool call before acceptance.")
                    force_prompt = build_force_tool_prompt(
                        problem_desc=problem_desc,
                        constraints=constraints,
                        target_code=target_code,
                        history=history,
                        weak_report=parsed_data,
                        memory_advice=memory_advice,
                    )
                    forced_response = llm.generate(force_prompt, temperature=0.0)
                    logger.debug(f"[Code Analyst] Round {round_num} forced-tool response:\n{forced_response[:300]}...")
                    forced_type, forced_data = parse_code_analyst_response(forced_response)
                    if forced_type == "tool_call":
                        tool_name = forced_data["tool"]
                        logger.info(f"[Code Analyst] Invoking forced tool call: {tool_name}")
                        tool_output = execute_tool(tool_name, forced_data.get("parameters", {}))
                        history.append(f"Action: Tool '{tool_name}' invoked.\nOutput:\n{tool_output}")
                        has_tool_evidence = True
                        response_text = llm.generate(prompt)
                        logger.debug(f"[Code Analyst] Round {round_num} post-tool response:\n{response_text[:300]}...")
                        continue
                    history.append("Action: Forced tool validation failed.\nError: Analyst did not return a valid tool call.")
                    break

                logger.info(f"[Code Analyst] Investigation complete in {round_num} rounds.")
                return parsed_data

            elif res_type == "tool_call":
                tool_name = parsed_data["tool"]
                logger.info(f"[Code Analyst] Invoking tool: {tool_name}")
                tool_output = execute_tool(tool_name, parsed_data.get("parameters", {}))
                history.append(f"Action: Tool '{tool_name}' invoked.\nOutput:\n{tool_output}")
                has_tool_evidence = True
                break

            elif res_type == "error":
                logger.warning(f"[Code Analyst] Validation Error: {parsed_data.get('message')}")
                repair_prompt = build_json_repair_prompt(
                    response_text,
                    problem_desc=problem_desc,
                    constraints=constraints,
                    target_code=target_code,
                    memory_advice=memory_advice,
                )
                repaired_response = llm.generate(repair_prompt, temperature=0.0)
                logger.debug(f"[Code Analyst] Round {round_num} repair response:\n{repaired_response[:300]}...")
                repaired_type, repaired_data = parse_code_analyst_response(repaired_response)
                if repaired_type == "final_report":
                    response_text = repaired_response
                    continue
                elif repaired_type == "tool_call":
                    response_text = repaired_response
                    continue
                history.append(f"Action: Attempted to submit response.\nError: {parsed_data.get('message')}")
                history.append("Action: JSON repair failed.\nError: Analyst still did not return valid JSON.")
                break

        round_num += 1

    logger.warning("[Code Analyst] Max rounds reached. Returning fallback Vulnerability Report.")
    return {
        "bug_class": "unknown",
        "confidence": "low",
        "evidence": ["Max analyst loop rounds reached without conclusion."],
        "suggested_route": "semantic",  # Default to semantic so Generator Matrix will still try
        "input_hypothesis": ["Max random limits"]
    }
