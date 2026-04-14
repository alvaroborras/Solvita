"""Generate Tests Node - Create test cases for the problem"""

from typing import Dict, Any, List, Optional, Set, Tuple, TYPE_CHECKING
import json
import re
from pathlib import Path
import shutil
import subprocess
from loguru import logger
from src.llm import UnifiedLLMClient
from src.llm.unified_client import PromptTooLongError
from src.memory import MemoryClient, MemoryNamespace
from src.memory.client import render_oracle_plan_to_prompt_payload, resolve_oracle_item_ids_by_family_ids
from src.oracle.catalog import build_oracle_catalog
from src.oracle.selector import build_rule_based_oracle_plan
from src.oracle.trainability import classify_trainability
from src.oracle.evidence import build_accepted_artifact
from src.oracle.logging import build_oracle_event_payload
from src.oracle.oracle_memory_runtime import decide_oracle_memory_gate
from src.oracle.oracle_memory_policy import recipe_bucket_from_template_name
from src.oracle.types import OracleRoute
from src.utils.json_utils import parse_json_response
from src.utils.problem_utils import extract_problem_code
from src.utils.prompt_templates import get_nested_template, load_prompt_templates, render_template

if TYPE_CHECKING:
    from src.graph.state import SolvitaState, TestData


def _truncate_for_prompt(text: str, max_chars: int, label: str) -> str:
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    omitted = len(text) - max_chars
    return text[:head] + f"\n... [TRUNCATED {label} {omitted} CHARS] ...\n" + text[-tail:]


def _compact_json_for_prompt(value: Any, max_chars: int, label: str) -> str:
    rendered = json.dumps(value, indent=2, ensure_ascii=False)
    return _truncate_for_prompt(rendered, max_chars=max_chars, label=label)


def _compact_public_tests_for_prompt(public_tests: List[Dict[str, Any]], max_tests: int = 3, field_chars: int = 400) -> str:
    compact = []
    for pt in public_tests[:max_tests]:
        compact.append(
            {
                "input": _truncate_for_prompt(pt.get("input", ""), field_chars, "PUBLIC_INPUT"),
                "output": _truncate_for_prompt(pt.get("output", ""), field_chars, "PUBLIC_OUTPUT"),
            }
        )
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _log_prompt_size(stage: str, prompt: str, **sections: str) -> None:
    stats = ", ".join(f"{name}={len(value)}" for name, value in sections.items())
    logger.debug(f"[PROMPT:{stage}] total_chars={len(prompt)} | {stats}")


def _update_prompt_telemetry(
    telemetry: Optional[Dict[str, Any]],
    stage: Optional[str],
    prompt: str,
) -> None:
    if telemetry is None or not stage:
        return
    prompt_char_stats = telemetry.setdefault("prompt_char_stats", {})
    prompt_char_stats[stage] = max(prompt_char_stats.get(stage, 0), len(prompt))


def _generate_with_compact_retry(
    llm: UnifiedLLMClient,
    prompt_builder,
    *args,
    _telemetry: Optional[Dict[str, Any]] = None,
    _stage: Optional[str] = None,
    **kwargs,
) -> str:
    prompt = prompt_builder(*args, compact=False, **kwargs)
    _update_prompt_telemetry(_telemetry, _stage, prompt)
    try:
        return llm.generate(prompt)
    except PromptTooLongError:
        compact_prompt = prompt_builder(*args, compact=True, **kwargs)
        _update_prompt_telemetry(_telemetry, _stage, compact_prompt)
        if _telemetry is not None and _stage:
            _telemetry["compact_retry_count"] = _telemetry.get("compact_retry_count", 0) + 1
            stages = _telemetry.setdefault("compact_retry_stages", [])
            if _stage not in stages:
                stages.append(_stage)
        logger.warning("[TestGen] Prompt exceeded max tokens, retrying with compact prompt")
        return llm.generate(compact_prompt)


def _compute_certification_ratio(certified_count: int, target_count: int) -> float:
    if certified_count <= 0 or target_count <= 0:
        return 0.0
    return certified_count / float(target_count)


def _is_cyclic_equivalence_problem(problem_desc: str) -> bool:
    text = (problem_desc or "").lower()
    markers = (
        "cyclic",
        "same set of indices",
        "considered different if the set of indices",
        "wrap",
        "concatenating m copies",
    )
    return sum(1 for marker in markers if marker in text) >= 2


def _is_cyclic_sum_segment_count_problem(problem_desc: str) -> bool:
    text = (problem_desc or "").lower()
    markers = (
        "cyclic sequence",
        "segment",
        "sum of elements in the segment is divisible by k",
        "number of different segments",
        "same set of indices",
        "concatenating m copies",
    )
    return sum(1 for marker in markers if marker in text) >= 4


def _build_generator_advice(problem_desc: str, certification_mode: bool) -> str:
    lines = []
    if certification_mode:
        lines.extend(
            [
                "Certification mode: prefer structurally diverse but modest-size inputs that are easy to certify exactly.",
                "Prioritize semantic edge cases over maximum-size random stress.",
            ]
        )
    if _is_cyclic_equivalence_problem(problem_desc):
        lines.extend(
            [
                "This problem has cyclic/equivalence semantics. Prioritize cases that distinguish wrap-around from ordinary linear segments.",
                "Include cases where the full cycle is valid or invalid, because full-cycle deduplication is easy to get wrong.",
                "Include small n with very large m, repeated values, and total sum modulo k equal to 0 and non-zero.",
            ]
        )
    return "\n".join(lines)


def _build_checker_advice(problem_desc: str) -> str:
    if not _is_cyclic_equivalence_problem(problem_desc):
        return ""
    return (
        "Semantic warning: if the problem says two segment representations are the same when they correspond "
        "to the same set of indices on the cycle, your checker MUST enforce that exact equivalence relation. "
        "Do NOT count empty segments unless the statement explicitly allows them. If the full cycle has many "
        "representations, it must still count as one object."
    )


def _build_solver_advice(problem_desc: str) -> str:
    if not _is_cyclic_equivalence_problem(problem_desc):
        return ""
    lines = [
        "Semantic warning: do NOT reduce this to ordinary linear subarray counting unless you explicitly prove "
        "that the cyclic set-of-indices definition is preserved. Full-cycle representations and wrap-around "
        "identity are common sources of off-by-many bugs here. Prefer a direct small-scale enumerator of cyclic "
        "segments as sets of indices over a brittle closed-form formula."
    ]
    if _is_cyclic_sum_segment_count_problem(problem_desc):
        lines.append(
            "For cyclic segment-counting problems, equal prefix residues inside one linearized period are NOT "
            "sufficient when totalSum(b) mod k != 0. You must reason separately about wrap-around vs non-wrap "
            "segments, including the lifted boundary at position N, or use an explicitly justified doubled-array "
            "window formulation."
        )
    return " ".join(lines)


def _count_cyclic_divisible_segments_bruteforce(n: int, m: int, k: int, a: List[int]) -> int:
    total_positions = n * m
    if total_positions > 256:
        raise ValueError("bruteforce helper is only intended for modest certification inputs")

    b = a * m
    total_sum = sum(b)
    answer = 0
    for start in range(total_positions):
        segment_sum = 0
        for length in range(1, total_positions):
            segment_sum += b[(start + length - 1) % total_positions]
            if segment_sum % k == 0:
                answer += 1
    if total_sum % k == 0:
        answer += 1
    return answer % 1000000007


def _build_local_certified_tests(problem_desc: str) -> List[Dict[str, Any]]:
    if not _is_cyclic_sum_segment_count_problem(problem_desc):
        return []

    cases = [
        (1, 3, 2, [1]),
        (1, 4, 3, [1]),
        (2, 1, 5, [0, 1]),
        (3, 2, 5, [1, 1, 1]),
    ]

    certified = []
    for n, m, k, a in cases:
        expected = _count_cyclic_divisible_segments_bruteforce(n, m, k, a)
        certified.append(
            {
                "input": f"{n} {m} {k}\n{' '.join(map(str, a))}\n",
                "output": f"{expected}\n",
                "type": "edge",
                "description": "Local exact cyclic wrap certification case",
            }
        )
    return certified


def _normalize_generated_input(text: str) -> str:
    return text.strip() + "\n"


def _append_distinct_generated_input(
    generated_inputs: List[str],
    seen_inputs: Set[str],
    candidate_input: str,
) -> bool:
    normalized = _normalize_generated_input(candidate_input)
    if not normalized.strip() or normalized in seen_inputs:
        return False
    seen_inputs.add(normalized)
    generated_inputs.append(normalized)
    return True


def _build_checker_negative_output(expected_output: str) -> str:
    base = str(expected_output or "").rstrip("\n")
    if base:
        return base + "\n__CHECKER_NEGATIVE_TOKEN__\n"
    return "__CHECKER_NEGATIVE_TOKEN__\n"


def _validate_checker_on_public_tests(
    checker_exe: Path,
    public_tests: List[Dict[str, Any]],
    tests_dir: Path,
) -> Tuple[bool, str]:
    for i, pt in enumerate(public_tests):
        expected_output = pt.get("output", "")
        if not str(expected_output).strip():
            continue

        input_path = tests_dir / f"public_{i}.in"
        candidate_path = tests_dir / f"public_{i}.out"
        answer_path = tests_dir / f"public_{i}.ans"
        negative_path = tests_dir / f"public_{i}.bad.out"

        input_path.write_text(pt.get("input", ""), encoding="utf-8")
        candidate_path.write_text(expected_output, encoding="utf-8")
        answer_path.write_text(expected_output, encoding="utf-8")
        negative_path.write_text(_build_checker_negative_output(expected_output), encoding="utf-8")

        ok, err = run_checker(checker_exe, input_path, candidate_path, answer_path)
        if not ok:
            return False, f"Public test {i} failed on known-correct output: {err}"

        bad_ok, bad_err = run_checker(checker_exe, input_path, negative_path, answer_path)
        if bad_ok:
            return False, (
                f"Public test {i} malformed-output check failed: "
                "checker accepted output with trailing garbage"
            )
        if not bad_err:
            return False, f"Public test {i} malformed-output check failed without diagnostic"

    return True, ""


def _resolve_data_root(config: Dict[str, Any]) -> Path:
    configured = (config or {}).get("data_root")
    if configured:
        return Path(configured).resolve()
    return (Path(__file__).resolve().parents[2] / "data").resolve()


def _resolve_oracle_selection(
    state: "SolvitaState",
    config: Dict[str, Any],
    problem_desc: str,
    constraints: Dict[str, Any],
    canonical: Dict[str, Any],
    checker_exe: Optional[Path],
) -> Tuple[Any, str, List[str], Optional[Dict[str, Any]]]:
    raw_problem = state.get("raw_problem", {})
    trusted_checker_provenance = raw_problem.get("trusted_checker_provenance")
    trainability_class = classify_trainability(
        has_checker=checker_exe is not None,
        is_interactive=bool(raw_problem.get("interactive", False)),
        is_multi_answer=bool(raw_problem.get("is_multi_solution", False) or canonical.get("is_multi_solution", False)),
        has_trusted_checker=bool(trusted_checker_provenance),
        has_trusted_normalizer=bool(raw_problem.get("trusted_normalizer")),
    )
    oracle_plan = build_rule_based_oracle_plan(
        trainability_class=trainability_class,
        problem_tags=canonical.get("tags", []) or raw_problem.get("tags", []),
        problem_constraints=constraints,
        acceptance_mode=((config or {}).get("oracle") or {}).get("mode", "safe"),
    )
    catalog = build_oracle_catalog()
    primary_item = catalog[oracle_plan.primary_family_id]
    oracle_payload = render_oracle_plan_to_prompt_payload(oracle_plan, primary_item)
    oracle_advice = json.dumps(oracle_payload, indent=2)

    oracle_memory = MemoryClient(
        namespace=MemoryNamespace.ORACLE,
        config=config,
        problem_desc=problem_desc,
        canonical=canonical,
    )
    family_ids = [oracle_plan.primary_family_id]
    if oracle_plan.fallback_family_id:
        family_ids.append(oracle_plan.fallback_family_id)
    oracle_item_ids = resolve_oracle_item_ids_by_family_ids(oracle_memory, family_ids)
    return oracle_plan, oracle_advice, oracle_item_ids, trusted_checker_provenance


def _resolve_selected_family_id(solver_data: Dict[str, Any], oracle_plan: Any) -> str:
    candidate_family_ids = [oracle_plan.primary_family_id]
    if getattr(oracle_plan, "fallback_family_id", None):
        candidate_family_ids.append(oracle_plan.fallback_family_id)

    selected_family_id = solver_data.get("selected_family_id")
    if selected_family_id in candidate_family_ids:
        return selected_family_id
    return oracle_plan.primary_family_id


def _apply_oracle_acceptance_gate(
    *,
    route: str,
    generated_inputs: List[str],
    generated_outputs: List[str],
    confidence: float,
    threshold: float,
    trusted_checker_provenance: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not generated_inputs or not generated_outputs:
        return None
    if confidence < threshold:
        return None
    if route == "trusted_checker_backed_multi_answer" and not trusted_checker_provenance:
        return None

    oracle_route = (
        OracleRoute.TRUSTED_CHECKER_BACKED_MULTI
        if route == "trusted_checker_backed_multi_answer"
        else OracleRoute.EXACT_SINGLE_ANSWER
    )
    return build_accepted_artifact(
        route=oracle_route,
        input_text=generated_inputs[0],
        output_text=generated_outputs[0],
        verifier_provenance=trusted_checker_provenance,
        evidence={"source": "generate_tests"},
    )


def safe_problem_dir_name(raw_problem: Dict[str, Any]) -> str:
    '''
    生成安全目录名 data/generated/{problem_id}

    支持多种格式：
    - _metadata.problem_id: "1575_A"
    - _metadata.name: "1575_A. Another Sorting Problem"
    - _metadata.question_id: "1873_A"
    '''
    metadata = raw_problem.get("_metadata", {})

    # 尝试多个可能的字段
    problem_id = None
    for key in ("problem_id", "name", "question_id"):
        val = metadata.get(key)
        if val:
            problem_id = val
            break

    if not problem_id:
        return "unknown"

    # 如果是 "1575_A. Another Sorting Problem" 格式，只取 "1575_A"
    if isinstance(problem_id, str):
        # 提取 "数字_字母" 部分
        match = re.match(r"^(\d+_[A-Z]\d*)", problem_id)
        if match:
            problem_id = match.group(1)
        # 清理路径名中的非法字符
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", problem_id).strip("_")
        return safe or "unknown"

    return str(problem_id)

from src.utils.cpp_execution import compile_cpp, run_program, run_checker, sanitize_cpp, ExecutionLimits


def build_generator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str, memory_advice: str = "", compact: bool = False) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    advice_block = f"\n{memory_advice}\n" if memory_advice else ""
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000 if not compact else 4000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000 if not compact else 1200, "CONSTRAINTS")
    compact_public_tests = _compact_public_tests_for_prompt(public_tests, max_tests=3 if not compact else 2, field_chars=400 if not compact else 180)
    prompt = render_template(
        "generate_tests.generator",
        PROBLEM_DESC=compact_problem_desc,
        CONSTRAINTS=compact_constraints,
        PUBLIC_TESTS=compact_public_tests,
        FEEDBACK_BLOCK=feedback_block,
        ADVICE_BLOCK=advice_block,
    )
    _log_prompt_size("generator", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=compact_public_tests, feedback=feedback_block, advice=advice_block)
    return prompt


def build_validator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str, compact: bool = False) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000 if not compact else 4000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000 if not compact else 1200, "CONSTRAINTS")
    compact_public_tests = _compact_public_tests_for_prompt(public_tests, max_tests=3 if not compact else 2, field_chars=400 if not compact else 180)
    prompt = render_template(
        "generate_tests.validator",
        PROBLEM_DESC=compact_problem_desc,
        CONSTRAINTS=compact_constraints,
        PUBLIC_TESTS=compact_public_tests,
        FEEDBACK_BLOCK=feedback_block,
    )
    _log_prompt_size("validator", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=compact_public_tests, feedback=feedback_block)
    return prompt


def build_checker_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str, compact: bool = False) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    checker_advice = _build_checker_advice(problem_desc)
    checker_advice_block = f"\n{checker_advice}\n" if checker_advice else ""
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000 if not compact else 4000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000 if not compact else 1200, "CONSTRAINTS")
    compact_public_tests = _compact_public_tests_for_prompt(public_tests, max_tests=3 if not compact else 2, field_chars=400 if not compact else 180)
    prompt = render_template(
        "generate_tests.checker",
        PROBLEM_DESC=compact_problem_desc,
        CONSTRAINTS=compact_constraints,
        PUBLIC_TESTS=compact_public_tests,
        CHECKER_ADVICE_BLOCK=checker_advice_block,
        FEEDBACK_BLOCK=feedback_block,
    )
    _log_prompt_size("checker", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=compact_public_tests, feedback=feedback_block)
    return prompt


def build_solver_stage_guidance(attempt: int) -> str:
    root = load_prompt_templates()
    if attempt <= 1:
        return str(get_nested_template(root, "generate_tests.solver_stage.attempt_1")).strip()
    if attempt == 2:
        return str(get_nested_template(root, "generate_tests.solver_stage.attempt_2")).strip()
    return str(get_nested_template(root, "generate_tests.solver_stage.attempt_3_plus")).strip()


def build_solver_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], templates_json: str, feedback: str, attempt: int = 1, compact: bool = False) -> str:
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000 if not compact else 4000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000 if not compact else 1200, "CONSTRAINTS")
    compact_templates = _truncate_for_prompt(templates_json, 6000 if not compact else 2500, "ORACLE_ADVICE")
    compact_feedback = _truncate_for_prompt(feedback, 4000 if not compact else 1500, "SOLVER_FEEDBACK") if feedback else ""
    feedback_block = f"\nPrevious attempt issues:\n{compact_feedback}\n" if compact_feedback else ""

    pt_block = ""
    for i, pt in enumerate(public_tests[: (3 if not compact else 2)]):
        inp = _truncate_for_prompt(pt.get('input', '').strip(), 400 if not compact else 180, 'PUBLIC_INPUT')
        out = _truncate_for_prompt(pt.get('output', '').strip(), 400 if not compact else 180, 'PUBLIC_OUTPUT')
        pt_block += f"\n--- Test {i} ---\nInput:\n{inp}\nExpected Output:\n{out}\n"

    stage_guidance = build_solver_stage_guidance(attempt)
    solver_advice = _build_solver_advice(problem_desc)
    solver_advice_block = f"\nProblem-specific guidance:\n{solver_advice}\n" if solver_advice else ""

    prompt = render_template(
        "generate_tests.solver",
        STAGE_GUIDANCE=stage_guidance,
        SOLVER_ADVICE_BLOCK=solver_advice_block,
        PROBLEM_DESC=compact_problem_desc,
        CONSTRAINTS=compact_constraints,
        PUBLIC_TESTS_BLOCK=pt_block,
        TEMPLATES_JSON=compact_templates,
        FEEDBACK_BLOCK=feedback_block,
    )
    _log_prompt_size("solver", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=pt_block, templates=compact_templates, feedback=feedback_block)
    return prompt


def summarize_public_solver_failure(
    test_id: str,
    test_input: str,
    expected: str,
    actual: str,
    error: str,
    diagnostic_info: str = "",
) -> str:
    failure_type = "runtime_error" if not actual.strip() else "wrong_answer"
    failure = {
        "id": test_id,
        "type": failure_type,
        "input": test_input,
        "expected": expected,
        "actual": actual,
        "output": actual,
        "message": error,
        "error": error,
    }
    return format_solver_feedback([failure], 1, 1, diagnostic_info=diagnostic_info)


def finalize_solver_certification(
    training_mode: bool,
    original_input_count: int,
    current_partial_inputs: List[str],
    current_partial_outputs: List[str],
    best_partial_inputs: List[str],
    best_partial_outputs: List[str],
    solver_ok: bool,
) -> Dict[str, Any]:
    best_inputs = best_partial_inputs
    best_outputs = best_partial_outputs
    if len(current_partial_inputs) > len(best_inputs):
        best_inputs = list(current_partial_inputs)
        best_outputs = list(current_partial_outputs)

    if solver_ok:
        return {
            "accepted": True,
            "inputs": current_partial_inputs,
            "outputs": current_partial_outputs,
            "message": f"FULLY CERTIFIED: {len(current_partial_inputs)}/{original_input_count}",
        }

    if best_inputs:
        return {
            "accepted": True,
            "inputs": best_inputs,
            "outputs": best_outputs,
            "message": f"PARTIALLY CERTIFIED: {len(best_inputs)}/{original_input_count}",
        }

    return {
        "accepted": False,
        "inputs": [],
        "outputs": [],
        "message": f"CERTIFIED 0/{original_input_count}" if training_mode else "No certified generated tests",
    }


def format_solver_feedback(failed: List[Dict], total_run: int, total_verify: int, diagnostic_info: str = "") -> str:
    """
    Format solver feedback for LLM iteration.
    """
    def _compress_block(text: str, head: int = 8, tail: int = 8, marker: str = "[TRUNCATED]") -> str:
        if not text:
            return ""
        lines = text.splitlines()
        if len(lines) <= head + tail + 1:
            return text
        kept = lines[:head] + [f"... {marker} {len(lines) - head - tail} LINES ..."] + lines[-tail:]
        return "\n".join(kept)

    def _truncate_inline(text: str, max_chars: int = 240) -> str:
        text = str(text or "")
        if len(text) <= max_chars:
            return text
        head = max_chars // 2
        tail = max_chars - head
        omitted = len(text) - max_chars
        return text[:head] + f" ... [TRUNCATED {omitted} CHARS] ... " + text[-tail:]

    lines = []
    
    if diagnostic_info:
        lines.append("CRITICAL: Diagnostic scan (AddressSanitizer) detected a crash:")
        lines.append("```")
        lines.append(_compress_block(diagnostic_info, head=10, tail=10, marker="[ASAN TRUNCATED]"))
        lines.append("```")
        lines.append("Focus on fixing the memory/undefined behavior reported above first.")
        lines.append("")

    lines.append(f"Your code failed {len(failed)} out of {total_run} cases tested ({total_verify} total):")

    # Pick representative failures
    picked = []
    runtime_errors = [f for f in failed if f.get("type") == "runtime_error"]
    wrong_answers = [f for f in failed if f.get("type") == "wrong_answer"]
    
    if runtime_errors: picked.append(runtime_errors[0])
    if wrong_answers: picked.extend(wrong_answers[:2])
    if not picked: picked = failed[:3]

    for f in picked[:3]:
        ftype = f.get("type", "unknown")
        # Extract traces if available from stderr
        stderr = f.get("stderr", "")
        traces = []
        if stderr:
             all_traces = [line for line in stderr.splitlines() if line.startswith("TRACE:")]
             if len(all_traces) > 15:
                 head = all_traces[:5]
                 tail = all_traces[-5:]
                 mid_idx = len(all_traces) // 2
                 mid = all_traces[mid_idx-2 : mid_idx+3]
                 traces = head + ["... [TRACED BUT SAMPLED/SKIPPED] ..."] + mid + ["... [TRACED BUT SAMPLED/SKIPPED] ..."] + tail
             else:
                 traces = all_traces[:15]
        
        if ftype == "runtime_error":
            lines.append(f"  Runtime error on test {f.get('id', '?')}:")
            lines.append(f"    Error: {f.get('error', f.get('message', '?'))}")
        elif ftype == "wrong_answer":
            lines.append(f"  Wrong answer on test {f.get('id', '?')}:")
            actual = _truncate_inline(str(f.get('output', f.get('actual', '?'))), max_chars=200)
            lines.append(f"    Output (truncated): {actual}")
            if f.get("error"):
                lines.append(f"    Checker message:    {_truncate_inline(f.get('error'), max_chars=240)}")
        
        inp = _truncate_inline(str(f.get('input', '')), max_chars=200)
        if inp: lines.append(f"    Input (truncated): {inp}")
        
        if traces:
            lines.append("    Execution Traces (from stderr):")
            lines.extend([f"      {t}" for t in traces])

    lines.append("")
    lines.append("Please fix these issues and regenerate the code.")
    return "\n".join(lines)



def _run_training_runner(runner, inp: str):
    """Run a correct_solution runner and return (returncode, stdout)."""
    import subprocess as _sp
    kind, path = runner
    limits = ExecutionLimits.default_run()
    if kind == "cpp":
        rc, stdout, _ = run_program(path, inp, limits=limits)
        return rc, stdout
    else:
        try:
            r = _sp.run(
                ["python3", str(path)],
                input=inp, capture_output=True, text=True,
                timeout=limits.wall_seconds or 10,
            )
            return r.returncode, r.stdout
        except _sp.TimeoutExpired:
            return 124, ""
        except Exception:
            return -1, ""


def _build_oracle_memory_decision(
    *,
    config: Dict[str, Any],
    selected_template_name: str,
    gate_decision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_template_name = str(selected_template_name or "").strip()
    selected_action_bucket = (
        recipe_bucket_from_template_name(normalized_template_name)
        if normalized_template_name
        else None
    )
    oracle_memory_mode = (
        config.get("trainable_memory", {}).get("oracle_memory_mode", "off")
        if isinstance(config, dict)
        else "off"
    )
    decision = {
        "memory_mode": oracle_memory_mode,
        "policy_version": "rule_v1",
        "selected_action": selected_action_bucket,
        "candidate_action_set": [selected_action_bucket] if selected_action_bucket else [],
        "exploration_flag": False,
        "replacement_action": None,
        "applied": False,
        "reason": "gate_not_run",
    }
    if not normalized_template_name:
        decision["reason"] = "template_unknown"
        return decision
    if gate_decision:
        decision.update(gate_decision)
        decision["selected_action"] = selected_action_bucket
        decision["candidate_action_set"] = [selected_action_bucket]
        decision["replacement_action"] = None
        decision["exploration_flag"] = False
        decision["memory_mode"] = oracle_memory_mode
        decision["policy_version"] = "rule_v1"
    return decision


def _evaluate_oracle_memory_gate_if_ready(
    *,
    config: Dict[str, Any],
    selected_template_name: str,
) -> Dict[str, Any]:
    normalized_template_name = str(selected_template_name or "").strip()
    if not normalized_template_name:
        return {
            "applied": False,
            "reason": "template_unknown",
            "selected_action": None,
            "replacement_action": None,
            "candidate_action_set": [],
            "exploration_flag": False,
        }
    return decide_oracle_memory_gate(
        config=config,
        selected_template_name=normalized_template_name,
    )


def generate_tests_node(state: "SolvitaState") -> Dict[str, Any]:
    logger.info("[Node] Generating test cases")

    config = state["config"]
    raw_problem = state.get("raw_problem", {})
    oracle_cfg = (config or {}).get("oracle") or {}
    oracle_mode = oracle_cfg.get("mode", "safe")
    oracle_accept_threshold = float(
        oracle_cfg.get(
            "accept_threshold",
            0.95 if oracle_mode == "safe" else 0.80 if oracle_mode == "balanced" else 0.0,
        )
    )
    
    # Prefer canonical problem representation if available
    canonical = state["problem"].get("canonical", {})
    if canonical:
        # Build compact problem statement from canonical JSON
        problem_desc = f"""Objective: {canonical.get('objective', '')}
Inputs: {json.dumps(canonical.get('inputs', {}), indent=2)}
Outputs: {json.dumps(canonical.get('outputs', {}), indent=2)}
Constraints: {json.dumps(canonical.get('constraints', {}), indent=2)}"""
    else:
        # Fallback to original description
        problem_desc = state["problem"].get("description", "")
    
    public_tests = state["problem"].get("public_tests", [])
    constraints = state["problem"].get("constraints", {})
    local_certified_tests = _build_local_certified_tests(problem_desc)
    solver_public_tests = list(public_tests) + list(local_certified_tests)

    def role_client(role: str) -> UnifiedLLMClient:
        role_cfg = UnifiedLLMClient.build_role_config(config, role)
        return UnifiedLLMClient(role_cfg)

    gen_llm = role_client("generator")
    val_llm = role_client("validator")
    chk_llm = role_client("checker")
    out_llm = role_client("output")

    llm_calls = 0
    max_iter = 3
    target_count = int((state.get("config", {}) or {}).get("generate_tests_target_count", 200))
    output_max_iter = 5

    problem_code = extract_problem_code(raw_problem)
    problem_dir = safe_problem_dir_name(raw_problem)
    data_root = _resolve_data_root(config)
    generated_root = data_root / "generated" / (problem_code or problem_dir)
    code_dir = generated_root / "code"
    tests_dir = generated_root / "tests"
    code_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "_probe.txt").write_text("probe", encoding="utf-8")

    ac_path = data_root / "problems" / "ac" / f"{problem_code}.cpp" if problem_code else None
    if ac_path and ac_path.exists():
        logger.info(f"[AC] Lookup: {ac_path} -> FOUND")
    else:
        logger.info(f"[AC] Lookup: {ac_path} -> NOT FOUND")
        target_count = min(target_count, 50)

    certification_mode = not (ac_path and ac_path.exists())
    generator_advice = _build_generator_advice(problem_desc, certification_mode=certification_mode)
    if local_certified_tests:
        logger.info(
            f"[CERT] Added {len(local_certified_tests)} local exact certification case(s) "
            "for cyclic wrap semantics"
        )

    generated_inputs: List[str] = []
    gen_feedback = ""
    val_feedback = ""
    validator_exe: Optional[Path] = None
    oracle_telemetry: Dict[str, Any] = {
        "prompt_char_stats": {},
        "compact_retry_count": 0,
        "compact_retry_stages": [],
    }

    for attempt in range(1, max_iter + 1):
        gen_response = _generate_with_compact_retry(
            gen_llm,
            build_generator_prompt,
            problem_desc,
            constraints,
            public_tests,
            gen_feedback,
            memory_advice=generator_advice,
            _telemetry=oracle_telemetry,
            _stage="generator",
        )
        llm_calls += 1
        (code_dir / f"generator_{attempt}_raw.txt").write_text(gen_response, encoding="utf-8")
        try:
            gen_data = parse_json_response(gen_response)
            generator_cpp = gen_data.get("generator_cpp", "")
        except Exception:
            gen_feedback = "Invalid JSON for generator"
            continue

        gen_path = code_dir / f"generator_{attempt}.cpp"
        gen_path.write_text(generator_cpp, encoding="utf-8")
        gen_exe = code_dir / f"generator_{attempt}.exe"
        gen_ok, gen_log = compile_cpp(gen_path, gen_exe, include_testlib=True)
        if not gen_ok:
            gen_feedback = f"Generator compile failed: {gen_log}"
            (code_dir / f"generator_{attempt}.log").write_text(gen_log, encoding="utf-8")
            continue

        val_response = _generate_with_compact_retry(
            val_llm,
            build_validator_prompt,
            problem_desc,
            constraints,
            public_tests,
            val_feedback,
            _telemetry=oracle_telemetry,
            _stage="validator",
        )
        llm_calls += 1
        logger.info(f"[GV] Validator response length: {len(val_response)}")
        (code_dir / f"validator_{attempt}_raw.txt").write_text(val_response, encoding="utf-8")
        try:
            val_data = parse_json_response(val_response)
            validator_cpp = val_data.get("validator_cpp", "")
        except Exception:
            val_feedback = "Invalid JSON for validator"
            continue

        val_path = code_dir / f"validator_{attempt}.cpp"
        val_path.write_text(validator_cpp, encoding="utf-8")
        val_exe = code_dir / f"validator_{attempt}.exe"
        val_ok, val_log = compile_cpp(val_path, val_exe, include_testlib=True)
        if not val_ok:
            val_feedback = f"Validator compile failed: {val_log}"
            (code_dir / f"validator_{attempt}.log").write_text(val_log, encoding="utf-8")
            continue
        validator_exe = val_exe

        generated_inputs = []
        seen_generated_inputs: Set[str] = set()
        duplicate_inputs = 0
        attempts = 0
        max_attempts = target_count * 5
        while len(generated_inputs) < target_count and attempts < max_attempts:
            seed = str(1000 + attempts)
            output_path = tests_dir / f"gen_{attempt}_{attempts}.in"
            try:
                with output_path.open("w", encoding="utf-8") as out_file:
                    result = subprocess.run(
                        [str(gen_exe), seed],
                        stdout=out_file,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=2,
                    )
            except subprocess.TimeoutExpired:
                attempts += 1
                gen_feedback = "Generator timed out"
                (tests_dir / f"gen_{attempt}_{attempts}_runtime_err.txt").write_text("timeout", encoding="utf-8")
                continue

            attempts += 1
            if result.returncode != 0:
                err = result.stderr or ""
                gen_feedback = f"Generator runtime error: {err}"
                (tests_dir / f"gen_{attempt}_{attempts}_runtime_err.txt").write_text(err, encoding="utf-8")
                continue

            out = output_path.read_text(encoding="utf-8")
            normalized_out = _normalize_generated_input(out)
            if not normalized_out.strip():
                gen_feedback = "Generator produced empty output"
                (tests_dir / f"gen_{attempt}_{attempts}_empty.txt").write_text("EMPTY", encoding="utf-8")
                continue

            if normalized_out in seen_generated_inputs:
                duplicate_inputs += 1
                (tests_dir / f"gen_{attempt}_{attempts}_duplicate.txt").write_text("DUPLICATE", encoding="utf-8")
                continue

            v_code, _, v_err = run_program(val_exe, input_text=normalized_out, limits=ExecutionLimits.default_run())
            if v_code != 0:
                val_feedback = f"Validator rejected input: {v_err}"
                (tests_dir / f"gen_{attempt}_{attempts}_reject.txt").write_text(v_err, encoding="utf-8")
                continue
            _append_distinct_generated_input(generated_inputs, seen_generated_inputs, normalized_out)

        if duplicate_inputs > 0:
            logger.info(
                f"[GV] Generator attempt {attempt} produced {duplicate_inputs} duplicate input(s); "
                f"kept {len(generated_inputs)} distinct valid cases"
            )

        if len(generated_inputs) >= target_count:
            break

        gen_feedback = (
            f"Only produced {len(generated_inputs)} distinct valid inputs out of {target_count} target"
        )
        if duplicate_inputs > 0:
            gen_feedback += (
                f". Detected {duplicate_inputs} duplicate outputs across different seeds. "
                "Do not hardcode one case; use rnd.next(...) so different seeds usually produce different valid inputs."
            )

    if not generated_inputs:
        logger.warning("[GV] Failed to generate inputs, using public tests only")

    generated_outputs: List[str] = []
    checker_exe: Optional[Path] = None
    ac_exe: Optional[Path] = None
    training_mode: bool = bool(state.get("training_mode", False))
    training_runner = state.get("training_runner", None)  # (kind, path) tuple from train_oracle.py
    last_solver_compile_ok = False
    last_public_self_check_pass = False
    last_probe_pack_pass = False
    checker_fallback_used = False
    solver_attempt_count = 0
    selected_template_name = ""

    if ac_path and ac_path.exists():
        ac_exe = code_dir / "ac_solution.exe"
        ac_ok, ac_log = compile_cpp(ac_path, ac_exe, include_testlib=True)
        if not ac_ok:
            logger.warning(f"[AC] Compile failed: {ac_log}")
            ac_exe = None

    if generated_inputs and ac_exe:
        for idx, inp in enumerate(generated_inputs):
            code, out, err = run_program(ac_exe, input_text=inp, limits=ExecutionLimits.default_run())
            if code != 0:
                logger.warning(f"[AC] Runtime error on input {idx}: {err}")
                generated_outputs = []
                break
            generated_outputs.append(out.strip() + "\n")

    if generated_inputs and not generated_outputs:
        checker_feedback = ""
        for attempt in range(1, max_iter + 1):
            checker_response = _generate_with_compact_retry(
                chk_llm,
                build_checker_prompt,
                problem_desc,
                constraints,
                public_tests,
                checker_feedback,
                _telemetry=oracle_telemetry,
                _stage="checker",
            )
            llm_calls += 1
            (code_dir / f"checker_{attempt}_raw.txt").write_text(checker_response, encoding="utf-8")
            try:
                checker_data = parse_json_response(checker_response)
                checker_cpp = checker_data.get("checker_cpp", "")
            except Exception:
                checker_feedback = "Invalid JSON for checker (must return pure JSON with checker_cpp)"
                continue

            checker_path = code_dir / f"checker_{attempt}.cpp"
            checker_path.write_text(checker_cpp, encoding="utf-8")
            candidate_checker_exe = code_dir / f"checker_{attempt}.exe"  # 先用临时变量
            checker_ok, checker_log = compile_cpp(checker_path, candidate_checker_exe, include_testlib=True)
            if not checker_ok:
                checker_feedback = f"Checker compile failed: {checker_log}"
                continue

            public_ok, checker_err = _validate_checker_on_public_tests(
                candidate_checker_exe,
                public_tests,
                tests_dir,
            )
            if not public_ok:
                checker_feedback = checker_err

            if public_ok:
                checker_exe = candidate_checker_exe  # 自检也通过后才正式赋值
                break

        if checker_exe is None:
            checker_fallback_used = True
            logger.warning("[CHECKER] Failed to build checker, using exact string matching fallback")

        oracle_plan, oracle_advice, oracle_item_ids, trusted_checker_provenance = _resolve_oracle_selection(
            state=state,
            config=config,
            problem_desc=problem_desc,
            constraints=constraints,
            canonical=canonical,
            checker_exe=checker_exe,
        )

        output_feedback = ""
        diagnostic_info = ""
        solver_ok = False
        selected_family_id = oracle_plan.primary_family_id
        best_partial_inputs: list = []
        best_partial_outputs: list = []
        for attempt in range(1, output_max_iter + 1):
            solver_attempt_count = attempt
            solver_response = _generate_with_compact_retry(
                out_llm,
                build_solver_prompt,
                problem_desc, constraints, public_tests, oracle_advice,
                output_feedback,
                attempt=attempt,
                _telemetry=oracle_telemetry,
                _stage="solver",
            )
            llm_calls += 1
            (code_dir / f"solver_bf_{attempt}_raw.txt").write_text(solver_response, encoding="utf-8")
            try:
                solver_data = parse_json_response(solver_response)
                solver_cpp = solver_data.get("solver_cpp", "")
                selected_family_id = _resolve_selected_family_id(solver_data, oracle_plan)
                tmpl_name = solver_data.get("template_name", "UNKNOWN")
                selected_template_name = tmpl_name
                logger.info(f"[SOLVER] LLM chose template: {tmpl_name}")
            except Exception:
                output_feedback = "Invalid JSON (must return pure JSON with template_name and solver_cpp)"
                continue

            solver_cpp = sanitize_cpp(solver_cpp)
            solver_path = code_dir / f"solver_bf_{attempt}.cpp"
            solver_path.write_text(solver_cpp, encoding="utf-8")
            solver_exe = code_dir / f"solver_bf_{attempt}.exe"
            solver_compile_ok, solver_log = compile_cpp(solver_path, solver_exe, include_testlib=False)
            last_solver_compile_ok = solver_compile_ok
            if not solver_compile_ok:
                output_feedback = f"Solver compile failed:\n{solver_log}"
                (code_dir / f"solver_bf_{attempt}.log").write_text(solver_log, encoding="utf-8")
                continue

            # ===== CRITICAL: Self-check solver on public tests first =====
            solver_public_ok = True
            solver_limits = ExecutionLimits.default_run()
            if hasattr(solver_limits, "wall_seconds") and solver_limits.wall_seconds is not None:
                solver_limits.wall_seconds = max(solver_limits.wall_seconds, 10.0)
            
            diagnostic_info = "" # Reset diagnostic info for this attempt
            public_actual = ""
            
            for pi, pt in enumerate(solver_public_tests):
                pt_input = pt.get("input", "")
                pt_expected = pt.get("output", "")
                test_label = f"{pt.get('type', 'public')}_{pi}"
                if not pt_input.strip() or not pt_expected.strip():
                    continue
                try:
                    s_code, s_out, s_err = run_program(solver_exe, input_text=pt_input, limits=solver_limits)
                except Exception:
                    s_code, s_out, s_err = 1, "", "exception"
                
                public_actual = s_out
                if s_code != 0 or not s_out.strip():
                    solver_public_ok = False
                    # TLE (code 124) usually isn't a memory bug, don't trigger ASan for it
                    if s_code != 0 and s_code != 124:
                        logger.info(f"[DIAGNOSTIC] Solver crashed on public test {pi} (code {s_code}). Triggering ASan...")
                        diag_exe = code_dir / f"solver_bf_{attempt}_diag.exe"
                        diag_ok, diag_log = compile_cpp(solver_path, diag_exe, diagnostic=True)
                        if diag_ok:
                            _, _, diag_err = run_program(diag_exe, input_text=pt_input, limits=ExecutionLimits.diagnostic_compile())
                            diagnostic_info = diag_err
                        else:
                            diagnostic_info = f"Diagnostic compile failed:\n{diag_log}"
                    
                    output_feedback = summarize_public_solver_failure(
                        test_id=test_label,
                        test_input=pt_input,
                        expected=pt_expected,
                        actual=s_out,
                        error=f"Solver crashed on self-check test {test_label}: {s_err}",
                        diagnostic_info=diagnostic_info,
                    )
                    break
                
                if checker_exe:
                    pub_in = tests_dir / f"solver_pub_{pi}.in"
                    pub_out = tests_dir / f"solver_pub_{pi}.out"
                    pub_ans = tests_dir / f"solver_pub_{pi}.ans"
                    pub_in.write_text(pt_input, encoding="utf-8")
                    pub_out.write_text(s_out.strip() + "\n", encoding="utf-8")
                    pub_ans.write_text(pt_expected.strip() + "\n", encoding="utf-8")
                    chk_ok, chk_msg = run_checker(checker_exe, pub_in, pub_out, pub_ans)
                    if not chk_ok:
                        solver_public_ok = False
                        output_feedback = summarize_public_solver_failure(
                            test_id=test_label,
                            test_input=pt_input,
                            expected=pt_expected,
                            actual=s_out,
                            error=f"Solver wrong on self-check test {test_label}: {chk_msg}",
                            diagnostic_info=diagnostic_info,
                        )
                        break
                else:
                    # Exact string matching, ignoring trailing whitespace per line (CP judge standard)
                    def _norm(s): return "\n".join(l.rstrip() for l in s.strip().splitlines())
                    if _norm(s_out) != _norm(pt_expected):
                        solver_public_ok = False
                        output_feedback = summarize_public_solver_failure(
                            test_id=test_label,
                            test_input=pt_input,
                            expected=pt_expected,
                            actual=s_out,
                            error=f"Solver wrong on self-check test {test_label}",
                            diagnostic_info=diagnostic_info,
                        )
                        break

            # ── Public self-check result (now OUTSIDE for-pi loop) ──────────
            if not solver_public_ok:
                logger.warning(f"[SOLVER] solver_bf_{attempt} FAILED public self-check: {output_feedback}")
                continue  # continues 'for attempt in range(...)' loop
            last_public_self_check_pass = True

            # ===== Micro-test verification — runs ONCE per attempt ==========
            failed = []
            timeout_or_runtime = False
            total_run = 0
            # Training mode: accumulate correct tests instead of tracking failures
            partial_certified_inputs: list = []
            partial_certified_outputs: list = []
            _original_input_count = len(generated_inputs)
            logger.info(f"[SOLVER] Verifying solver_bf_{attempt} on {_original_input_count} micro-tests...")
            for i, inp in enumerate(generated_inputs):
                total_run += 1
                input_path = tests_dir / f"gen_{i}.in"
                output_path = tests_dir / f"gen_{i}.out"
                cleaned_input = inp.rstrip("\n") + "\n"
                input_path.write_text(cleaned_input, encoding="utf-8")

                solver_limits = ExecutionLimits.default_run()
                if hasattr(solver_limits, "wall_seconds") and solver_limits.wall_seconds is not None:
                    solver_limits.wall_seconds = max(solver_limits.wall_seconds, 10.0)

                try:
                    code, out, err = run_program(solver_exe, input_text=inp, limits=solver_limits)
                except Exception as ex:
                    code, out, err = 1, "", str(ex)

                if code != 0 or not out.strip():
                    timeout_or_runtime = True
                    # Again, check if we should trigger ASan
                    if code != 0 and code != 124:
                        logger.info(f"[DIAGNOSTIC] Solver crashed on micro-test {i} (code {code}). Triggering ASan...")
                        diag_exe = code_dir / f"solver_bf_{attempt}_diag.exe"
                        diag_ok, _ = compile_cpp(solver_path, diag_exe, diagnostic=True)
                        if diag_ok:
                            _, _, diag_err = run_program(diag_exe, input_text=inp, limits=ExecutionLimits.diagnostic_compile())
                            diagnostic_info = diag_err

                    failed.append({"type": "runtime_error", "id": i, "error": err or "runtime error", "input": inp, "stderr": err})
                    break

                output_path.write_text(out.strip() + "\n", encoding="utf-8")

                # Certification priority:
                # 1. ac_exe  — offline AC file (most authoritative)
                # 2. training_runner — correct_solution from dataset (training mode)
                # 3. checker_exe  — production workflow
                # 4. fallback  — trust solver (passed public self-check)
                if ac_exe and generated_outputs:
                    if out.strip() != generated_outputs[i].strip():
                        failed.append({"type": "wrong_answer", "id": i,
                                       "error": "Mismatch with ac_solution", "input": inp, "output": out, "stderr": err})
                        if len(failed) >= 5:
                            break
                    else:
                        partial_certified_inputs.append(inp)
                        partial_certified_outputs.append(out.strip() + "\n")
                elif training_runner is not None:
                    # Training mode: accumulate correct tests (partial certification)
                    # We do NOT populate `failed` here — wrong tests are silently skipped
                    ref_rc, ref_out = _run_training_runner(training_runner, inp)
                    if ref_rc == 0:
                        def _norm(s): return "\n".join(l.rstrip() for l in s.strip().splitlines())
                        if _norm(out) == _norm(ref_out):
                            partial_certified_inputs.append(inp)
                            partial_certified_outputs.append(out.strip() + "\n")
                        # Wrong answer: silently skip — we keep only certified outputs
                    # ref_rc != 0: correct_solution itself failed on this input — skip
                elif checker_exe:
                    ok, chk_err = run_checker(checker_exe, input_path, output_path, output_path)
                    if not ok:
                        failed.append({"type": "wrong_answer", "id": i,
                                       "error": chk_err, "input": inp, "output": out, "stderr": err})
                        if len(failed) >= 5:
                            break
                    else:
                        partial_certified_inputs.append(inp)
                        partial_certified_outputs.append(out.strip() + "\n")
                else:
                    partial_certified_inputs.append(inp)
                    partial_certified_outputs.append(out.strip() + "\n")
                # else: no verifier — trust solver passed public self-check

            # ── Post-loop: determine success / failure ──────────────────────
            if training_runner is not None:
                result = finalize_solver_certification(
                    training_mode=True,
                    original_input_count=_original_input_count,
                    current_partial_inputs=partial_certified_inputs,
                    current_partial_outputs=partial_certified_outputs,
                    best_partial_inputs=best_partial_inputs,
                    best_partial_outputs=best_partial_outputs,
                    solver_ok=(not failed),
                )
                best_partial_inputs = result["inputs"]
                best_partial_outputs = result["outputs"]
                if result["accepted"]:
                    generated_inputs = result["inputs"]
                    generated_outputs = result["outputs"]
                    solver_ok = True
                    last_probe_pack_pass = True
                    logger.info(f"[SOLVER] solver_bf_{attempt} {result['message']}")
                    break

                logger.warning(f"[SOLVER] solver_bf_{attempt} {result['message']}")
                output_feedback = format_solver_feedback(failed, total_run, _original_input_count, diagnostic_info=diagnostic_info)
                if not timeout_or_runtime:
                    output_feedback = f"All {total_run} outputs differed from correct_solution. Re-think the algorithm."
            else:
                result = finalize_solver_certification(
                    training_mode=False,
                    original_input_count=_original_input_count,
                    current_partial_inputs=partial_certified_inputs,
                    current_partial_outputs=partial_certified_outputs,
                    best_partial_inputs=best_partial_inputs,
                    best_partial_outputs=best_partial_outputs,
                    solver_ok=(not failed),
                )
                best_partial_inputs = result["inputs"]
                best_partial_outputs = result["outputs"]
                if result["accepted"] and not failed:
                    generated_inputs = result["inputs"]
                    generated_outputs = result["outputs"]
                    solver_ok = True
                    last_probe_pack_pass = True
                    logger.info(f"[SOLVER] solver_bf_{attempt} {result['message']}")
                    break

                logger.warning(f"[SOLVER] solver_bf_{attempt} FAILED: {len(failed)}/{total_run} micro-tests failed")
                output_feedback = format_solver_feedback(failed, total_run, len(generated_inputs), diagnostic_info=diagnostic_info)
                (tests_dir / f"solver_bf_{attempt}_failed.txt").write_text(output_feedback, encoding="utf-8")

            if not solver_ok:
                logger.warning("[OUTPUT] Solver-based output generation failed, using public tests only")

        if not solver_ok:
            result = finalize_solver_certification(
                training_mode=training_mode or training_runner is not None,
                original_input_count=len(generated_inputs),
                current_partial_inputs=[],
                current_partial_outputs=[],
                best_partial_inputs=best_partial_inputs,
                best_partial_outputs=best_partial_outputs,
                solver_ok=False,
            )
            if result["accepted"]:
                generated_inputs = result["inputs"]
                generated_outputs = result["outputs"]
                solver_ok = True
                logger.info(f"[SOLVER] {result['message']}")

    # ========== Cleanup Phase ==========
    # Remove stale temporary input files from failed iterations
    # Keep only the final gen_*.in/out files that correspond to the successful inputs
    if (generated_inputs and generated_outputs) or generated_inputs:
        import glob
        import shutil
        logger.info("[CLEANUP] Removing stale test files from failed iterations...")
        
        # Count and remove all gen_*_*.in files (temporary inputs from failed attempts)
        stale_inputs = glob.glob(str(tests_dir / "gen_*_*.in"))
        stale_count = 0
        for stale_file in stale_inputs:
            try:
                Path(stale_file).unlink()
                stale_count += 1
            except Exception as e:
                logger.debug(f"Failed to remove {Path(stale_file).name}: {e}")
        
        if stale_count > 0:
            logger.info(f"[CLEANUP] Removed {stale_count} stale input files (gen_*_*.in)")
        
        # Also remove temporary marker files from failed validation/generation attempts
        for pattern in ["gen_*_*_reject.txt", "gen_*_*_empty.txt", "gen_*_*_runtime_err.txt",
                        "gen_*_*_duplicate.txt",
                        "solver_*_*_failed.txt", "solver_*_*_failed.json"]:
            stale_markers = glob.glob(str(tests_dir / pattern))
            for f in stale_markers:
                try:
                    Path(f).unlink()
                except:
                    pass

    generated_tests = []
    for pt in public_tests:
        generated_tests.append(
            {
                "input": pt.get("input", ""),
                "expected_output": pt.get("output", ""),
                "type": "public",
                "description": "Public test case",
            }
        )

    for pt in local_certified_tests:
        generated_tests.append(
            {
                "input": pt.get("input", ""),
                "expected_output": pt.get("output", ""),
                "type": pt.get("type", "edge"),
                "description": pt.get("description", "Local exact certification case"),
            }
        )

    if generated_inputs and generated_outputs:
        for inp, out in zip(generated_inputs, generated_outputs):
            generated_tests.append(
                {
                    "input": inp,
                    "expected_output": out,
                    "type": "generated",
                    "description": "Generated test case",
                }
            )

    test_counts = {
        "public": sum(1 for t in generated_tests if t["type"] == "public"),
        "edge": sum(1 for t in generated_tests if t["type"] == "edge"),
        "corner": sum(1 for t in generated_tests if t["type"] == "corner"),
        "random": sum(1 for t in generated_tests if t["type"] == "random"),
        "generated": sum(1 for t in generated_tests if t["type"] == "generated"),
    }

    # Compute solver cert_ratio for graduated reward in training mode
    _cert_count = sum(1 for t in generated_tests if t["type"] == "generated")
    _cert_ratio = _compute_certification_ratio(_cert_count, target_count)

    tests = {
        "generated_tests": generated_tests,
        "total_tests": len(generated_tests),
        "test_results": [],
        "passed_tests": 0,
        "pass_rate": 0.0,
        "cert_ratio": _cert_ratio,   # fraction of the 200 target micro-tests that were certified
        "certified_count": _cert_count,
        "certified_target_count": target_count,
        "pending_execution": False,
        "ready": True,
        "checker_exe": str(checker_exe) if checker_exe else None,
        "validator_exe": str(validator_exe) if validator_exe else None,
        "oracle_route": oracle_plan.route.value if 'oracle_plan' in locals() else None,
        "accepted_artifact_kind": None,
        "verifier_provenance": trusted_checker_provenance if 'trusted_checker_provenance' in locals() else None,
        "certification_evidence": [
            {
                "compile_success": last_solver_compile_ok,
                "public_self_check_pass": last_public_self_check_pass,
                "probe_pack_pass": last_probe_pack_pass,
            }
        ],
        "oracle_primary_family_id": oracle_plan.primary_family_id if 'oracle_plan' in locals() else None,
        "oracle_fallback_family_id": oracle_plan.fallback_family_id if 'oracle_plan' in locals() else None,
        "oracle_selected_family_id": selected_family_id if 'selected_family_id' in locals() else None,
        "candidate_family_pool": [oracle_plan.primary_family_id] + ([oracle_plan.fallback_family_id] if 'oracle_plan' in locals() and oracle_plan.fallback_family_id else []) if 'oracle_plan' in locals() else [],
        "oracle_compile_success": last_solver_compile_ok,
        "oracle_public_self_check_pass": last_public_self_check_pass,
        "oracle_probe_pack_pass": last_probe_pack_pass,
        "checker_fallback_used": checker_fallback_used,
        "solver_attempt_count": solver_attempt_count,
        "selected_template_name": selected_template_name,
        "prompt_char_stats": oracle_telemetry.get("prompt_char_stats", {}),
        "compact_retry_count": oracle_telemetry.get("compact_retry_count", 0),
    }
    accepted_artifact = None
    if 'oracle_plan' in locals():
        confidence = 1.0 if solver_ok and generated_inputs and generated_outputs else 0.0
        accepted_artifact = _apply_oracle_acceptance_gate(
            route=oracle_plan.route.value,
            generated_inputs=generated_inputs,
            generated_outputs=generated_outputs,
            confidence=confidence,
            threshold=oracle_accept_threshold,
            trusted_checker_provenance=trusted_checker_provenance,
        )
        tests["accepted_artifact_kind"] = accepted_artifact["kind"] if accepted_artifact else None

    oracle_memory_gate_decision = _evaluate_oracle_memory_gate_if_ready(
        config=config,
        selected_template_name=selected_template_name,
    )
    oracle_memory_decision = _build_oracle_memory_decision(
        config=config,
        selected_template_name=selected_template_name,
        gate_decision=oracle_memory_gate_decision,
    )
    tests["oracle_memory_decision"] = oracle_memory_decision

    return {
        "tests": tests,
        "oracle_memory_decision": oracle_memory_decision,
        "oracle_event_metadata": build_oracle_event_payload(
            problem_hash="",
            trainability_class=tests.get("oracle_route"),
            candidate_family_pool=tests.get("candidate_family_pool", []),
            selected_family_ids=[
                family_id for family_id in [tests.get("oracle_selected_family_id")] if family_id
            ],
            selector_version="rule_v1",
            propensity=1.0,
            certification_route=tests.get("oracle_route"),
            verifier_provenance=tests.get("verifier_provenance"),
            decision="accept" if accepted_artifact else "abstain",
            artifact_kind=tests.get("accepted_artifact_kind"),
            cost={"llm_calls": llm_calls},
            certified_count=tests.get("certified_count", 0),
            certified_target_count=tests.get("certified_target_count", 0),
            cert_ratio=tests.get("cert_ratio", 0.0),
            checker_fallback_used=tests.get("checker_fallback_used", False),
            solver_attempt_count=tests.get("solver_attempt_count", 0),
            selected_template_name=tests.get("selected_template_name", ""),
            prompt_char_stats=tests.get("prompt_char_stats", {}),
            compact_retry_count=tests.get("compact_retry_count", 0),
            evidence={"certification_evidence": tests.get("certification_evidence", [])},
            memory_mode=oracle_memory_decision["memory_mode"],
            policy_version=oracle_memory_decision["policy_version"],
            candidate_action_set=oracle_memory_decision["candidate_action_set"],
            selected_action=oracle_memory_decision["selected_action"],
            exploration_flag=oracle_memory_decision["exploration_flag"],
        ),
        "execution_log": [
            f"Generated {len(generated_tests)} test cases",
            f"  Public: {test_counts['public']}, Edge: {test_counts['edge']}, "
            f"Corner: {test_counts['corner']}, Random: {test_counts['random']}, "
            f"Other: {test_counts['generated']}",
        ],
        "llm_calls": llm_calls,
        "oracle_memory_item_ids": oracle_item_ids if 'oracle_item_ids' in locals() else [],
    }
