import json
import re
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.nodes._chat_utils import chat_with_history, build_chat_compaction_context
from src.utils.python_execution import run_python
from src.utils.cpp_execution import compile_cpp, run_program, ExecutionLimits
from src.utils.prompt_utils import compact_json_for_prompt, compact_list_for_prompt, truncate_for_prompt
from src.utils.prompt_templates import get_nested_template, load_prompt_templates, render_template

MAX_ANALYST_HISTORY_ENTRIES = 2
MAX_ANALYST_HISTORY_CHARS = 6000
MAX_CPP_PROBE_CHARS = 12000


def _analyst_system_prompt() -> str:
    tpl = get_nested_template(load_prompt_templates(), "code_analyst.system")
    return str(tpl).strip()


def _format_history_for_prompt(history: List[str]) -> str:
    if not history:
        return "No actions taken yet."

    history_text = "\n\n".join(history[-MAX_ANALYST_HISTORY_ENTRIES:])
    if len(history_text) > MAX_ANALYST_HISTORY_CHARS:
        history_text = "[... trimmed analyst history ...]\n" + history_text[-MAX_ANALYST_HISTORY_CHARS:]
    return history_text


def _extract_json_candidate(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1].strip()
        if candidate:
            return candidate

    return text


def _analyst_llm_generate(
    llm: UnifiedLLMClient,
    prompt: str,
    *,
    temperature: float = 0.0,
    messages_history: list = None,
    new_messages_acc: list = None,
    compaction_context: Optional[Dict[str, Any]] = None,
    compaction_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate with history support, with fallback for legacy test stubs."""
    system_prompt = _analyst_system_prompt()

    if messages_history is None:
        generate_with_system = getattr(type(llm), "generate_with_system", None)
        if callable(generate_with_system):
            try:
                return llm.generate_with_system(system_prompt, prompt, temperature=temperature)
            except TypeError as exc:
                if "temperature" not in str(exc):
                    raise
                return llm.generate_with_system(system_prompt, prompt)
        return llm.generate(prompt, temperature=temperature)

    history = messages_history
    response, new_msgs, persisted_messages = chat_with_history(
        llm,
        history,
        prompt,
        system_content=system_prompt,
        temperature=temperature,
        compaction_context=compaction_context,
        compaction_config=compaction_config,
    )
    if new_messages_acc is not None:
        new_messages_acc.extend(new_msgs)
    messages_history[:] = persisted_messages
    return response



def parse_code_analyst_response(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Parses the LLM response to determine if it is a tool call or the final report.
    Strips markdown code blocks (`json`) if present.
    Returns:
        (response_type, parsed_dict)
        where response_type is either "tool_call", "final_report", or "error".
    """
    text = _extract_json_candidate(text)
        
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
        if len(cpp_code) > MAX_CPP_PROBE_CHARS:
            return (
                "Error: C++ probe too large for analyst tool. "
                f"Limit is {MAX_CPP_PROBE_CHARS} characters."
            )
            
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


def build_analyst_prompt(problem_desc: str, constraints: Dict[str, Any], target_code: str, history: List[str], memory_advice: str = "", compact: bool = False) -> str:
    problem_desc = truncate_for_prompt(problem_desc, 8000 if not compact else 4000, "PROBLEM_DESC")
    constraints_json = compact_json_for_prompt(constraints, 2500 if not compact else 1200, "CONSTRAINTS")
    history_items = compact_list_for_prompt(
        history[-MAX_ANALYST_HISTORY_ENTRIES:],
        MAX_ANALYST_HISTORY_ENTRIES,
        1800 if not compact else 600,
        "HISTORY",
    )
    history_text = _format_history_for_prompt(history_items) if history_items else "No actions taken yet."
    target_code = truncate_for_prompt(target_code, 14000 if not compact else 6000, "TARGET_CODE")
    advice_section = ""
    if memory_advice:
        advice_section = f"\nHACKER STRATEGY ADVICE:\n{truncate_for_prompt(memory_advice, 2500 if not compact else 1000, 'MEMORY_ADVICE')}\n"

    return render_template(
        "code_analyst.main",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_JSON=constraints_json,
        TARGET_CODE=target_code,
        ADVICE_SECTION=advice_section,
        HISTORY_TEXT=history_text,
    )


def build_json_repair_prompt(
    previous_response: str,
    problem_desc: str,
    constraints: Dict[str, Any],
    target_code: str,
    memory_advice: str = "",
    compact: bool = False,
) -> str:
    previous_response = truncate_for_prompt(previous_response, 4000 if not compact else 1500, "PREVIOUS_RESPONSE")
    problem_desc = truncate_for_prompt(problem_desc, 7000 if not compact else 3000, "PROBLEM_DESC")
    constraints_json = compact_json_for_prompt(constraints, 2500 if not compact else 1200, "CONSTRAINTS")
    target_code = truncate_for_prompt(target_code, 12000 if not compact else 5000, "TARGET_CODE")
    advice_section = ""
    if memory_advice:
        advice_section = f"\nHACKER STRATEGY ADVICE:\n{truncate_for_prompt(memory_advice, 2500 if not compact else 1000, 'MEMORY_ADVICE')}\n"

    return render_template(
        "code_analyst.json_repair",
        PREVIOUS_RESPONSE=previous_response,
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_JSON=constraints_json,
        TARGET_CODE=target_code,
        ADVICE_SECTION=advice_section,
    )


def build_force_tool_prompt(
    problem_desc: str,
    constraints: Dict[str, Any],
    target_code: str,
    history: List[str],
    weak_report: Dict[str, Any],
    memory_advice: str = "",
    compact: bool = False,
) -> str:
    problem_desc = truncate_for_prompt(problem_desc, 7000 if not compact else 3000, "PROBLEM_DESC")
    constraints_json = compact_json_for_prompt(constraints, 2500 if not compact else 1200, "CONSTRAINTS")
    history_items = compact_list_for_prompt(
        history[-MAX_ANALYST_HISTORY_ENTRIES:],
        MAX_ANALYST_HISTORY_ENTRIES,
        1800 if not compact else 600,
        "HISTORY",
    )
    history_text = _format_history_for_prompt(history_items) if history_items else "No actions taken yet."
    weak_report_json = compact_json_for_prompt(weak_report, 3000 if not compact else 1200, "WEAK_REPORT")
    target_code = truncate_for_prompt(target_code, 12000 if not compact else 5000, "TARGET_CODE")
    advice_section = ""
    if memory_advice:
        advice_section = f"\nHACKER STRATEGY ADVICE:\n{truncate_for_prompt(memory_advice, 2500 if not compact else 1000, 'MEMORY_ADVICE')}\n"

    return render_template(
        "code_analyst.force_tool",
        PROBLEM_DESC=problem_desc,
        CONSTRAINTS_JSON=constraints_json,
        TARGET_CODE=target_code,
        ADVICE_SECTION=advice_section,
        WEAK_REPORT_JSON=weak_report_json,
        HISTORY_TEXT=history_text,
    )


def should_force_tool_validation(report: Dict[str, Any], has_tool_evidence: bool) -> bool:
    if has_tool_evidence:
        return False
    return report.get("bug_class") == "unknown" or report.get("confidence") == "low"

def run_code_analyst(state: Dict[str, Any], llm: UnifiedLLMClient, max_rounds: int = 5, memory_advice: str = "", messages_history: list = None) -> Tuple[Dict[str, Any], List[Dict[str, str]]] | Dict[str, Any]:
    """
    Executes the Code Analyst loop (up to `max_rounds` times).
    Returns the parsed report, and only returns appended messages when history threading is enabled.
    """
    logger.info("[Code Analyst] Starting investigation...")

    problem_desc = state.get("problem", {}).get("description", "")
    constraints = state.get("problem", {}).get("constraints", {})
    target_code = state.get("solution", {}).get("code", "")

    history = []
    has_tool_evidence = False
    round_num = 1
    prompt_compact = False
    history_enabled = messages_history is not None
    msg_history = list(messages_history) if history_enabled else None
    compaction_context = build_chat_compaction_context(state, node_name="code_analyst")
    compaction_config = state.get("config")
    all_new_msgs: List[Dict[str, str]] = []

    while round_num <= max_rounds:
        prompt = build_analyst_prompt(problem_desc, constraints, target_code, history, memory_advice=memory_advice, compact=prompt_compact)
        try:
            response_text = _analyst_llm_generate(
                llm,
                prompt,
                messages_history=msg_history,
                new_messages_acc=all_new_msgs,
                compaction_context=compaction_context,
                compaction_config=compaction_config,
            )
        except PromptTooLongError:
            if prompt_compact:
                raise
            prompt_compact = True
            logger.warning("[Code Analyst] Prompt exceeded max tokens, retrying in compact mode")
            continue
        
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
                        compact=prompt_compact,
                    )
                    try:
                        forced_response = _analyst_llm_generate(
                            llm,
                            force_prompt,
                            temperature=0.0,
                            messages_history=msg_history,
                            new_messages_acc=all_new_msgs,
                            compaction_context=compaction_context,
                            compaction_config=compaction_config,
                        )
                    except PromptTooLongError:
                        if prompt_compact:
                            raise
                        prompt_compact = True
                        force_prompt = build_force_tool_prompt(
                            problem_desc=problem_desc,
                            constraints=constraints,
                            target_code=target_code,
                            history=history,
                            weak_report=parsed_data,
                            memory_advice=memory_advice,
                            compact=True,
                        )
                        forced_response = _analyst_llm_generate(
                            llm,
                            force_prompt,
                            temperature=0.0,
                            messages_history=msg_history,
                            new_messages_acc=all_new_msgs,
                            compaction_context=compaction_context,
                            compaction_config=compaction_config,
                        )
                    logger.debug(f"[Code Analyst] Round {round_num} forced-tool response:\n{forced_response[:300]}...")
                    forced_type, forced_data = parse_code_analyst_response(forced_response)
                    if forced_type == "tool_call":
                        tool_name = forced_data["tool"]
                        logger.info(f"[Code Analyst] Invoking forced tool call: {tool_name}")
                        tool_output = execute_tool(tool_name, forced_data.get("parameters", {}))
                        history.append(f"Action: Tool '{tool_name}' invoked.\nOutput:\n{tool_output}")
                        has_tool_evidence = True
                        prompt = build_analyst_prompt(problem_desc, constraints, target_code, history, memory_advice=memory_advice, compact=prompt_compact)
                        response_text = _analyst_llm_generate(
                            llm,
                            prompt,
                            messages_history=msg_history,
                            new_messages_acc=all_new_msgs,
                            compaction_context=compaction_context,
                            compaction_config=compaction_config,
                        )
                        logger.debug(f"[Code Analyst] Round {round_num} post-tool response:\n{response_text[:300]}...")
                        continue
                    history.append("Action: Forced tool validation failed.\nError: Analyst did not return a valid tool call.")
                    break

                logger.info(f"[Code Analyst] Investigation complete in {round_num} rounds.")
                if history_enabled:
                    return parsed_data, all_new_msgs
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
                    compact=prompt_compact,
                )
                try:
                    repaired_response = _analyst_llm_generate(
                        llm,
                        repair_prompt,
                        temperature=0.0,
                        messages_history=msg_history,
                        new_messages_acc=all_new_msgs,
                        compaction_context=compaction_context,
                        compaction_config=compaction_config,
                    )
                except PromptTooLongError:
                    if prompt_compact:
                        raise
                    prompt_compact = True
                    repair_prompt = build_json_repair_prompt(
                        response_text,
                        problem_desc=problem_desc,
                        constraints=constraints,
                        target_code=target_code,
                        memory_advice=memory_advice,
                        compact=True,
                    )
                    repaired_response = _analyst_llm_generate(
                        llm,
                        repair_prompt,
                        temperature=0.0,
                        messages_history=msg_history,
                        new_messages_acc=all_new_msgs,
                        compaction_context=compaction_context,
                        compaction_config=compaction_config,
                    )
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
    fallback_report = {
        "bug_class": "unknown",
        "confidence": "low",
        "evidence": ["Max analyst loop rounds reached without conclusion."],
        "suggested_route": "semantic",
        "input_hypothesis": ["Max random limits"]
    }
    if history_enabled:
        return fallback_report, all_new_msgs
    return fallback_report
