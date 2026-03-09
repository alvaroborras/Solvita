"""Generate Tests Node - Create test cases for the problem"""

from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
import json
import re
from pathlib import Path
import shutil
import subprocess
from loguru import logger
from src.llm import UnifiedLLMClient
from src.memory import MemoryClient, MemoryNamespace
from src.utils.json_utils import parse_json_response
from src.utils.problem_utils import extract_problem_code

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
        match = re.match(r"^(\d+_[A-Z])", problem_id)
        if match:
            problem_id = match.group(1)
        # 清理路径名中的非法字符
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", problem_id).strip("_")
        return safe or "unknown"

    return str(problem_id)

from src.utils.cpp_execution import compile_cpp, run_program, run_checker, sanitize_cpp, ExecutionLimits


def build_generator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str, memory_advice: str = "") -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    advice_block = f"\n{memory_advice}\n" if memory_advice else ""
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000, "CONSTRAINTS")
    compact_public_tests = _compact_public_tests_for_prompt(public_tests, max_tests=3, field_chars=400)
    prompt = f"""You are a generator agent. Write a C++17 program that outputs exactly one valid test case to stdout.

Hard requirements:
- Use testlib: #include "testlib.h"
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Call registerGen(argc, argv, 1)
- Use rnd.next(...) for randomness (no std::random, no srand/rand)
- Do not parse or set a random seed inside the program
- Do not print any extra text
- Keep individual string lengths small (2-6 characters) unless constraints strictly dictate otherwise.
- For n strings of length m, ensure n <= 26^m (number of possible unique strings)
- Use std::unordered_set<std::string> for deduplication

Minimal skeleton (illustrative only):
#include "testlib.h"
#include <unordered_set>
int main(int argc, char* argv[]) {{
  registerGen(argc, argv, 1);
  // Choose m first, then limit n based on 26^m
  int m = rnd.next(2, 6);
  long long maxStrings = 1;
  for (int i = 0; i < m; i++) {{ maxStrings *= 26; }}
  long long maxN = std::min(200LL, (long long)(maxStrings * 0.8));
  int n = rnd.next(1, (int)maxN);
  std::cout << n << " " << m << std::endl;
  std::unordered_set<std::string> seen;
  for (int i = 0; i < n; i++) {{
    std::string s;
    do {{
      s = "";
      for (int j = 0; j < m; j++) {{
        s += char('A' + rnd.next(0, 25));
      }}
    }} while (seen.count(s));
    seen.insert(s);
    std::cout << s << std::endl;
  }}
  return 0;
}}

The program must produce ONE valid input instance that satisfies all constraints.

Problem Description:
{compact_problem_desc}

Constraints:
{compact_constraints}

Public Tests:
{compact_public_tests}
{feedback_block}
{advice_block}
Return ONLY a JSON object. No other text, no markdown.
Schema:
{{"generator_cpp": "<complete C++17 source>"}}
"""
    _log_prompt_size("generator", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=compact_public_tests, feedback=feedback_block, advice=advice_block)
    return prompt



def build_validator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000, "CONSTRAINTS")
    compact_public_tests = _compact_public_tests_for_prompt(public_tests, max_tests=3, field_chars=400)
    prompt = f"""You are a validator agent. Write a C++17 program that reads one test case from stdin and validates it.

Hard requirements:
- Use testlib: #include "testlib.h"
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Call registerValidation(argc, argv)
- Use inf.readInt/readLong/readToken to parse input
- Use inf.readToken() WITHOUT pattern parameter to read arbitrary strings
- Use ensuref(...) to report specific constraint violations
- Include #include <unordered_set> if using unordered_set
- Exit 0 on success, non-zero on failure
- Do not print anything on success

Minimal skeleton (illustrative only):
#include "testlib.h"
#include <unordered_set>
int main(int argc, char* argv[]) {{
  registerValidation(argc, argv);
  int n = inf.readInt();
  inf.readSpace();
  int m = inf.readInt();
  inf.readEoln();
  ensuref(n >= 1, "n must be >= 1");
  std::string s = inf.readToken();
  inf.readEof();
  return 0;
}}

Problem Description:
{compact_problem_desc}

Constraints:
{compact_constraints}

Public Tests:
{compact_public_tests}
{feedback_block}
Return ONLY a JSON object. No other text, no markdown.
Schema:
{{"validator_cpp": "<complete C++17 source>"}}
"""
    _log_prompt_size("validator", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=compact_public_tests, feedback=feedback_block)
    return prompt



def build_checker_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000, "CONSTRAINTS")
    compact_public_tests = _compact_public_tests_for_prompt(public_tests, max_tests=3, field_chars=400)
    prompt = f"""You are a checker/verifier agent. Write a C++17 program that **independently verifies**
whether a candidate output is correct for a given input — WITHOUT needing any reference answer.

CRITICAL DESIGN PRINCIPLE:
Verifying a solution is far easier than computing it. Your checker must independently
determine correctness by re-deriving the answer or checking invariants, NOT by comparing
against a reference. DO NOT read from the `ans` stream at all.

Approach (choose one based on the problem):
A) For problems with a unique answer: Compute the correct answer yourself using a simple
   brute-force algorithm (even O(n^3) or O(n^4) is fine — checkers run on small data),
   then compare against the candidate output.
B) For problems with multiple valid answers: Read the candidate output and verify it
   satisfies all problem constraints (e.g., is it a valid permutation? Does the graph
   satisfy the required property? Is the value optimal?).

Hard requirements:
- Use testlib: #include "testlib.h"
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Call registerTestlibCmd(argc, argv)
- Read input via inf (the test input)
- Read candidate output via ouf (the output to verify)
- DO NOT read from ans — your checker must work without any reference answer
- Use quitf(_ok, "...") if the candidate output is correct
- Use quitf(_wa, "...") with a specific error message if incorrect
- Implement your own verification logic inside the checker

Minimal skeleton (approach A — unique answer):
#include "testlib.h"
#include <vector>
int main(int argc, char* argv[]) {{
  registerTestlibCmd(argc, argv);
  // 1. Read the input
  int n = inf.readInt();
  // ... read full input ...
  
  // 2. Compute the correct answer independently (brute force is OK)
  int expected = brute_force_solve(n, ...);
  
  // 3. Read and verify the candidate output
  int got = ouf.readInt();
  if (got != expected) quitf(_wa, "expected %d, got %d", expected, got);
  quitf(_ok, "ok");
}}

Minimal skeleton (approach B — multiple valid answers):
#include "testlib.h"
#include <vector>
int main(int argc, char* argv[]) {{
  registerTestlibCmd(argc, argv);
  // 1. Read the input
  int n = inf.readInt();
  
  // 2. Read the candidate output
  int answer = ouf.readInt();
  
  // 3. Verify it satisfies the problem constraints
  if (!is_valid(answer, ...)) quitf(_wa, "invalid answer");
  quitf(_ok, "ok");
}}

Problem Description:
{compact_problem_desc}

Constraints:
{compact_constraints}

Public Tests:
{compact_public_tests}
{feedback_block}
Return ONLY a JSON object. No other text, no markdown.
Schema:
{{
  "checker_cpp": "<complete C++17 source>"
}}
"""
    _log_prompt_size("checker", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=compact_public_tests, feedback=feedback_block)
    return prompt



def build_solver_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], templates_json: str, feedback: str, attempt: int = 1) -> str:
    compact_problem_desc = _truncate_for_prompt(problem_desc, 8000, "PROBLEM_DESC")
    compact_constraints = _compact_json_for_prompt(constraints, 3000, "CONSTRAINTS")
    compact_templates = _truncate_for_prompt(templates_json, 6000, "ORACLE_ADVICE")
    compact_feedback = _truncate_for_prompt(feedback, 4000, "SOLVER_FEEDBACK") if feedback else ""
    feedback_block = f"\nPrevious attempt issues:\n{compact_feedback}\n" if compact_feedback else ""
    
    # Format public tests clearly
    pt_block = ""
    for i, pt in enumerate(public_tests[:3]):  # Limit further to save prompt space
        inp = _truncate_for_prompt(pt.get('input', '').strip(), 400, 'PUBLIC_INPUT')
        out = _truncate_for_prompt(pt.get('output', '').strip(), 400, 'PUBLIC_OUTPUT')
        pt_block += f"\n--- Test {i} ---\nInput:\n{inp}\nExpected Output:\n{out}\n"
    
    trace_instruction = ""
    if attempt >= 3:
        trace_instruction = """
NOTE: You have failed multiple times. Please add strategic debug prints to stderr using:
std::cerr << "TRACE: [message] " << vars... << std::endl;
WARNING: DO NOT print inside tight loops. If tracing a loop with many iterations, 
only print every 10000th iteration (e.g., if(count % 10000 == 0)) or just at the start/end.
"""

    prompt = f"""You are a Brute-Force Oracle. Write a COMPLETE, COMPILABLE C++17 program that solves the following problem using exhaustive / brute-force search.

CRITICAL REQUIREMENTS:
1. Your code MUST be a complete standalone program with #include, main(), cin/cout.
2. Read input from stdin, write output to stdout, matching the exact I/O format shown in the public tests.
3. Use a brute-force / exhaustive approach. Correctness is the ONLY goal — ignore performance.
4. The program MUST compile with: g++ -std=c++17 -O2
{trace_instruction}
Problem Description:
{compact_problem_desc}

Constraints:
{compact_constraints}

Public Tests (your program MUST produce the exact expected output for these):
{pt_block}

Algorithmic Strategy Reference (use for inspiration, do NOT copy verbatim):
{compact_templates}

{feedback_block}
Return ONLY a JSON object. No markdown, no explanation.
Schema:
{{
  "template_name": "<name of the strategy you are using>",
  "solver_cpp": "<complete C++17 source code>"
}}
"""
    _log_prompt_size("solver", prompt, problem_desc=compact_problem_desc, constraints=compact_constraints, public_tests=pt_block, templates=compact_templates, feedback=feedback_block)
    return prompt



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


def generate_tests_node(state: "SolvitaState") -> Dict[str, Any]:
    logger.info("[Node] Generating test cases")

    config = state["config"]
    raw_problem = state.get("raw_problem", {})
    
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
    # NOTE: Use absolute SSD path to avoid filling root partition.
    _DATA_ROOT = Path("<workspace>/duture/solvita/data")
    generated_root = _DATA_ROOT / "generated" / (problem_code or problem_dir)
    code_dir = generated_root / "code"
    tests_dir = generated_root / "tests"
    code_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "_probe.txt").write_text("probe", encoding="utf-8")

    ac_path = _DATA_ROOT / "problems" / "ac" / f"{problem_code}.cpp" if problem_code else None
    if ac_path and ac_path.exists():
        logger.info(f"[AC] Lookup: {ac_path} -> FOUND")
    else:
        logger.info(f"[AC] Lookup: {ac_path} -> NOT FOUND")

    generated_inputs: List[str] = []
    gen_feedback = ""
    val_feedback = ""
    validator_exe: Optional[Path] = None

    for attempt in range(1, max_iter + 1):
        gen_prompt = build_generator_prompt(problem_desc, constraints, public_tests, gen_feedback, memory_advice="")
        gen_response = gen_llm.generate(gen_prompt)
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

        val_prompt = build_validator_prompt(problem_desc, constraints, public_tests, val_feedback)
        val_response = val_llm.generate(val_prompt)
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
            if not out.strip():
                gen_feedback = "Generator produced empty output"
                (tests_dir / f"gen_{attempt}_{attempts}_empty.txt").write_text("EMPTY", encoding="utf-8")
                continue

            v_code, _, v_err = run_program(val_exe, input_text=out, limits=ExecutionLimits.default_run())
            if v_code != 0:
                val_feedback = f"Validator rejected input: {v_err}"
                (tests_dir / f"gen_{attempt}_{attempts}_reject.txt").write_text(v_err, encoding="utf-8")
                continue
            generated_inputs.append(out.strip() + "\n")

        if len(generated_inputs) >= target_count:
            break

        gen_feedback = f"Only produced {len(generated_inputs)} valid inputs out of {target_count} target"

    if not generated_inputs:
        logger.warning("[GV] Failed to generate inputs, using public tests only")

    generated_outputs: List[str] = []
    checker_exe: Optional[Path] = None
    ac_exe: Optional[Path] = None
    training_mode: bool = bool(state.get("training_mode", False))
    training_runner = state.get("training_runner", None)  # (kind, path) tuple from train_oracle.py

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
            checker_prompt = build_checker_prompt(problem_desc, constraints, public_tests, checker_feedback)
            checker_response = chk_llm.generate(checker_prompt, temperature=0.0)
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

            public_ok = True
            for i, pt in enumerate(public_tests):
                input_path = tests_dir / f"public_{i}.in"
                candidate_path = tests_dir / f"public_{i}.out"
                answer_path = tests_dir / f"public_{i}.ans"
                input_path.write_text(pt.get("input", ""), encoding="utf-8")
                candidate_path.write_text(pt.get("output", ""), encoding="utf-8")
                answer_path.write_text(pt.get("output", ""), encoding="utf-8")
                ok, err = run_checker(candidate_checker_exe, input_path, candidate_path, answer_path)
                if not ok:
                    public_ok = False
                    checker_feedback = f"Public test {i} failed: {err}"
                    break

            if public_ok:
                checker_exe = candidate_checker_exe  # 自检也通过后才正式赋值
                break

        if checker_exe is None:
            logger.warning("[CHECKER] Failed to build checker, using exact string matching fallback")

        oracle_memory = MemoryClient(
            namespace=MemoryNamespace.ORACLE,
            config=config,
            problem_desc=problem_desc,
            canonical=canonical,
        )
        oracle_advice, oracle_item_ids = oracle_memory.get_injection(
            fsm_state="SOLVER",
            failure_type=None,
            attempt_count=0
        )

        output_feedback = ""
        diagnostic_info = ""
        solver_ok = False
        for attempt in range(1, output_max_iter + 1):
            solver_prompt = build_solver_prompt(
                problem_desc, constraints, public_tests, oracle_advice, 
                output_feedback, attempt=attempt
            )
            solver_response = out_llm.generate(solver_prompt)
            llm_calls += 1
            (code_dir / f"solver_bf_{attempt}_raw.txt").write_text(solver_response, encoding="utf-8")
            try:
                solver_data = parse_json_response(solver_response)
                solver_cpp = solver_data.get("solver_cpp", "")
                tmpl_name = solver_data.get("template_name", "UNKNOWN")
                logger.info(f"[SOLVER] LLM chose template: {tmpl_name}")
            except Exception:
                output_feedback = "Invalid JSON (must return pure JSON with template_name and solver_cpp)"
                continue

            solver_cpp = sanitize_cpp(solver_cpp)
            solver_path = code_dir / f"solver_bf_{attempt}.cpp"
            solver_path.write_text(solver_cpp, encoding="utf-8")
            solver_exe = code_dir / f"solver_bf_{attempt}.exe"
            solver_compile_ok, solver_log = compile_cpp(solver_path, solver_exe, include_testlib=False)
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
            
            for pi, pt in enumerate(public_tests):
                pt_input = pt.get("input", "")
                pt_expected = pt.get("output", "")
                if not pt_input.strip() or not pt_expected.strip():
                    continue
                try:
                    s_code, s_out, s_err = run_program(solver_exe, input_text=pt_input, limits=solver_limits)
                except Exception:
                    s_code, s_out, s_err = 1, "", "exception"
                
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
                    
                    output_feedback = f"Solver crashed on public test {pi}: {s_err}"
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
                        output_feedback = f"Solver wrong on public test {pi}: {chk_msg}"
                        break
                else:
                    # Exact string matching, ignoring trailing whitespace per line (CP judge standard)
                    def _norm(s): return "\n".join(l.rstrip() for l in s.strip().splitlines())
                    if _norm(s_out) != _norm(pt_expected):
                        solver_public_ok = False
                        output_feedback = f"Solver wrong on public test {pi}:\nExpected:\n{pt_expected.strip()}\nGot:\n{s_out.strip()}"  
                        break

            # ── Public self-check result (now OUTSIDE for-pi loop) ──────────
            if not solver_public_ok:
                logger.warning(f"[SOLVER] solver_bf_{attempt} FAILED public self-check: {output_feedback}")
                output_feedback = format_solver_feedback([], 0, 0, diagnostic_info=diagnostic_info) + "\n" + output_feedback
                continue  # continues 'for attempt in range(...)' loop

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
                # else: no verifier — trust solver passed public self-check

            # ── Post-loop: determine success / failure ──────────────────────
            if training_runner is not None:
                # Training mode: partial certification
                n_cert = len(partial_certified_inputs)
                if n_cert > 0:
                    generated_inputs = partial_certified_inputs
                    generated_outputs = partial_certified_outputs
                    solver_ok = True
                    if n_cert == _original_input_count:
                        logger.info(f"[SOLVER] solver_bf_{attempt} FULLY CERTIFIED: {n_cert}/{_original_input_count}")
                    else:
                        logger.info(f"[SOLVER] solver_bf_{attempt} PARTIALLY CERTIFIED: {n_cert}/{_original_input_count}")
                    break
                else:
                    logger.warning(f"[SOLVER] solver_bf_{attempt} CERTIFIED 0/{_original_input_count}")
                    output_feedback = format_solver_feedback(failed, total_run, _original_input_count, diagnostic_info=diagnostic_info)
                    if timeout_or_runtime:
                        # If it was a runtime error, the feedback is already set, and we should break
                        break
                    else:
                        # Otherwise, it was wrong answers, and we provide specific feedback
                        output_feedback = f"All {total_run} outputs differed from correct_solution. Re-think the algorithm."
            else:
                # Production mode: binary pass/fail (unchanged)
                if not failed:
                    generated_outputs = [
                        (tests_dir / f"gen_{i}.out").read_text(encoding="utf-8").strip() + "\n"
                        for i in range(len(generated_inputs))
                    ]
                    solver_ok = True
                    logger.info(f"[SOLVER] solver_bf_{attempt} PASSED all {len(generated_inputs)} tests (Certified!)")
                    break

                logger.warning(f"[SOLVER] solver_bf_{attempt} FAILED: {len(failed)}/{total_run} micro-tests failed")
                output_feedback = format_solver_feedback(failed, total_run, len(generated_inputs), diagnostic_info=diagnostic_info)
                (tests_dir / f"solver_bf_{attempt}_failed.txt").write_text(output_feedback, encoding="utf-8")

                if timeout_or_runtime:
                    break

            if not solver_ok:
                logger.warning("[OUTPUT] Solver-based output generation failed, using public tests only")

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
    _cert_ratio = (_cert_count / 200.0) if _cert_count > 0 else 0.0  # 200 is the target input count

    tests = {
        "generated_tests": generated_tests,
        "total_tests": len(generated_tests),
        "test_results": [],
        "passed_tests": 0,
        "pass_rate": 0.0,
        "cert_ratio": _cert_ratio,   # fraction of the 200 target micro-tests that were certified
        "pending_execution": False,
        "ready": True,
        "checker_exe": str(checker_exe) if checker_exe else None,
        "validator_exe": str(validator_exe) if validator_exe else None,
    }

    return {
        "tests": tests,
        "execution_log": [
            f"Generated {len(generated_tests)} test cases",
            f"  Public: {test_counts['public']}, Edge: {test_counts['edge']}, "
            f"Corner: {test_counts['corner']}, Random: {test_counts['random']}, "
            f"Other: {test_counts['generated']}",
        ],
        "llm_calls": llm_calls,
        "oracle_memory_item_ids": oracle_item_ids if 'oracle_item_ids' in locals() else [],
    }
