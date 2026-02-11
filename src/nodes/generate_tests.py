"""Generate Tests Node - Create test cases for the problem"""

from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING
import json
import re
from pathlib import Path
import shutil
import subprocess
from loguru import logger
from src.llm import UnifiedLLMClient

if TYPE_CHECKING:
    from src.graph.state import SolvitaState, TestData


def parse_json_response(response: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks

    Supports:
    - Pure JSON: {"key": "value"}
    - Markdown wrapped: ```json\n{"key": "value"}\n```
    - Generic code block: ```\n{"key": "value"}\n```
    """
    cleaned = response.strip()

    if "```json" in cleaned:
        parts = cleaned.split("```json")
        if len(parts) > 1:
            cleaned = parts[1].split("```")[0].strip()
    elif "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Response content: {cleaned[start : min(end + 1, start + 200)]}...")
                raise
        logger.error("Failed to parse JSON response: no JSON object found")
        logger.debug(f"Response content: {cleaned[:200]}...")
        raise


def extract_problem_code(raw_problem: Dict[str, Any]) -> Optional[str]:
    '''
    正则提取题号，用于AC解的路径拼接

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
        return None

    # 如果是 "1575_A. Another Sorting Problem" 格式，提取 "1575_A"
    if isinstance(problem_id, str):
        # 尝试匹配 "数字_字母" 格式
        match = re.match(r"^(\d+_[A-Z])", problem_id)
        if match:
            return match.group(1)
        # 如果已经是 "1575_A" 格式，直接返回
        match = re.match(r"^(\d+_[A-Z])$", problem_id)
        if match:
            return problem_id

    return None


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

from src.utils.cpp_execution import compile_cpp, run_program, run_checker, sanitize_cpp


def build_generator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    return f"""You are a generator agent. Write a C++17 program that outputs exactly one valid test case to stdout.

Hard requirements:
- Use testlib: #include "testlib.h"
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Call registerGen(argc, argv, 1)
- Use rnd.next(...) for randomness (no std::random, no srand/rand)
- Do not parse or set a random seed inside the program
- Do not print any extra text
- Keep individual string lengths small (2-6 characters)
- Limit n to <= 200 to keep output size manageable
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
{problem_desc}

Constraints:
{json.dumps(constraints, indent=2)}

Public Tests:
{json.dumps(public_tests, indent=2)}
{feedback_block}
Return ONLY a JSON object. No other text, no markdown.
Schema:
{{"generator_cpp": "<complete C++17 source>"}}
"""



def build_validator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    return f"""You are a validator agent. Write a C++17 program that reads one test case from stdin and validates it.

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
{problem_desc}

Constraints:
{json.dumps(constraints, indent=2)}

Public Tests:
{json.dumps(public_tests, indent=2)}
{feedback_block}
Return ONLY a JSON object. No other text, no markdown.
Schema:
{{"validator_cpp": "<complete C++17 source>"}}
"""



def build_checker_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    builtin = [
        "ncmp (ordered int64 sequence)",
        "rcmp4 (float sequence, abs/rel 1e-4)",
        "rcmp6 (float sequence, abs/rel 1e-6)",
        "rcmp9 (float sequence, abs/rel 1e-9)",
        "wcmp (token comparison)",
        "hcmp (big integers)",
        "nyesno (YES/NO case-insensitive)",
        "fcmp (full-text exact)",
    ]
    return f"""You are a checker agent. Decide whether the problem has multiple valid outputs.
If single-solution, implement a checker that computes the expected output and compares against the candidate output.
If multi-solution, implement a checker that validates the candidate output against the problem requirements.

Hard requirements:
- Use testlib: #include "testlib.h"
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Call registerTestlibCmd(argc, argv)
- Read input via inf, candidate output via ouf, reference answer via ans when applicable
- For multi-solution, ignore ans and validate output against requirements
- Use quitf(_ok/_wa/_fail) with specific error messages

Minimal skeleton (illustrative only):
#include "testlib.h"
int main(int argc, char* argv[]) {{
  registerTestlibCmd(argc, argv);
  int n = inf.readInt();
  int ansv = ans.readInt();
  int outv = ouf.readInt();
  if (outv != ansv) quitf(_wa, "mismatch");
  quitf(_ok, "ok");
}}

Input files:
- argv[1]: input file path
- argv[2]: output file path (candidate output)

Exit code:
- 0 if correct
- non-zero if incorrect (write a short error to stderr)

Built-in comparator types you can use inside your checker if needed:
{json.dumps(builtin, indent=2)}

Problem Description:
{problem_desc}

Constraints:
{json.dumps(constraints, indent=2)}

Public Tests:
{json.dumps(public_tests, indent=2)}
{feedback_block}
Return ONLY a JSON object. No other text, no markdown.
Schema:
{{
  "is_multi_solution": false,
  "checker_cpp": "<complete C++17 source>"
}}
"""



def build_solver_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], tier_instruction: str, feedback: str) -> str:
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    return f"""You are a solver agent. Write a complete C++17 program that reads a single test case from stdin and prints the correct output.

Core instruction:
- {tier_instruction}

Hard requirements:
- Output ONLY the C++17 source code, no markdown, no explanations
- Do NOT use non-standard headers like #include <bits/stdc++.h>
- Deterministic, no randomness
- Handle all edge cases
- Use standard libraries only
- Use fast I/O

Problem Description:
{problem_desc}

Constraints:
{json.dumps(constraints, indent=2)}

Public Tests:
{json.dumps(public_tests, indent=2)}
{feedback_block}
Return ONLY the C++17 code.
"""


def format_solver_feedback(failed: List[Dict], total_run: int, total_verify: int) -> str:
    """
    Format solver feedback for LLM iteration.

    Only include representative failures (up to 3) to keep prompt concise,
    plus actionable debugging guidance.
    """
    lines = [f"Your code failed {len(failed)} out of {total_run} cases tested ({total_verify} total):"]

    # Categorize failures
    compile_errors = [f for f in failed if f.get("type") == "compile_error"]
    runtime_errors = [f for f in failed if f.get("type") == "runtime_error"]
    wrong_answers = [f for f in failed if f.get("type") == "wrong_answer"]

    # Pick representative failures (up to 3 total)
    picked = []
    if compile_errors:
        picked.append(compile_errors[0])
    if runtime_errors:
        picked.append(runtime_errors[0])
    if wrong_answers:
        picked.extend(wrong_answers[:2])

    for f in picked[:3]:
        if f.get("type") == "compile_error":
            lines.append(f"  Compilation error:\n    {f.get('message', '?')[:500]}")
        elif f.get("type") == "runtime_error":
            lines.append(f"  Runtime error on test {f.get('id', '?')}:")
            lines.append(f"    Error: {f.get('message', '?')}")
        elif f.get("type") == "wrong_answer":
            lines.append(f"  Wrong answer on test {f.get('id', '?')}:")
            inp = f.get('input', '?')[:100]
            expected = f.get('expected', '?')[:100]
            actual = f.get('actual', '?')[:100]
            lines.append(f"    Input:    {inp}")
            lines.append(f"    Expected: {expected}")
            lines.append(f"    Actual:   {actual}")

    lines.append("")
    lines.append("Debug checklist (verify these in your code):")
    lines.append("  1. Index base: output should use 1-based indices (not 0-based)")
    lines.append("  2. Comparison logic: odd positions (1,3,5...) ascending, even positions descending")
    lines.append("  3. String length: all input strings have exactly m characters")
    lines.append("  4. Output format: numbers separated by spaces, ending with newline")
    lines.append("  5. Edge cases: n=1, or when strings differ at first position")

    lines.append("")
    lines.append("Please fix these issues and regenerate the code.")
    return "\n".join(lines)



def generate_tests_node(state: "SolvitaState") -> Dict[str, Any]:
    logger.info("[Node] Generating test cases")

    config = state["config"]
    raw_problem = state.get("raw_problem", {})
    problem_desc = state["problem"].get("description", "")
    public_tests = state["problem"].get("public_tests", [])
    constraints = state["problem"].get("constraints", {})

    role_models = {
        "generator": "claude-opus-4-5-20251101",
        "validator": "gpt-5.2",
        "checker": "gpt-5.2",
        "output": "gpt-5.2",
    }

    def role_client(role: str) -> UnifiedLLMClient:
        role_cfg = dict(config)
        role_cfg["model"] = role_models[role]
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
    generated_root = Path("data") / "generated" / (problem_code or problem_dir)
    code_dir = generated_root / "code"
    tests_dir = generated_root / "tests"
    code_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "_probe.txt").write_text("probe", encoding="utf-8")

    ac_path = Path("data") / "problems" / "ac" / f"{problem_code}.cpp" if problem_code else None
    if ac_path and ac_path.exists():
        logger.info(f"[AC] Lookup: {ac_path} -> FOUND")
    else:
        logger.info(f"[AC] Lookup: {ac_path} -> NOT FOUND")

    generated_inputs: List[str] = []
    gen_feedback = ""
    val_feedback = ""

    for attempt in range(1, max_iter + 1):
        gen_prompt = build_generator_prompt(problem_desc, constraints, public_tests, gen_feedback)
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

            v_code, _, v_err = run_program(val_exe, input_text=out, timeout=2)
            if v_code != 0:
                val_feedback = f"Validator rejected input: {v_err}"
                (tests_dir / f"gen_{attempt}_{attempts}_reject.txt").write_text(v_err, encoding="utf-8")
                continue
            generated_inputs.append(out.strip() + "\n")

        if len(generated_inputs) >= target_count:
            break

        gen_feedback = f"Only produced {len(generated_inputs)} valid inputs"

    if not generated_inputs:
        logger.warning("[GV] Failed to generate inputs, using public tests only")

    generated_outputs: List[str] = []
    ac_exe: Optional[Path] = None

    if ac_path and ac_path.exists():
        ac_exe = code_dir / "ac_solution.exe"
        ac_ok, ac_log = compile_cpp(ac_path, ac_exe, include_testlib=True)
        if not ac_ok:
            logger.warning(f"[AC] Compile failed: {ac_log}")
            ac_exe = None

    if generated_inputs and ac_exe:
        for idx, inp in enumerate(generated_inputs):
            code, out, err = run_program(ac_exe, input_text=inp, timeout=2)
            if code != 0:
                logger.warning(f"[AC] Runtime error on input {idx}: {err}")
                generated_outputs = []
                break
            generated_outputs.append(out.strip() + "\n")

    if generated_inputs and not generated_outputs:
        checker_feedback = ""
        checker_exe = None
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
            checker_exe = code_dir / f"checker_{attempt}.exe"
            checker_ok, checker_log = compile_cpp(checker_path, checker_exe, include_testlib=True)
            if not checker_ok:
                checker_feedback = f"Checker compile failed: {checker_log}"
                continue

            public_ok = True
            for i, pt in enumerate(public_tests):
                input_path = tests_dir / f"public_{i}.in"
                output_path = tests_dir / f"public_{i}.out"
                input_path.write_text(pt.get("input", ""), encoding="utf-8")
                output_path.write_text(pt.get("output", ""), encoding="utf-8")
                ok, err = run_checker(checker_exe, input_path, output_path, output_path)
                if not ok:
                    public_ok = False
                    checker_feedback = f"Public test {i} failed: {err}"
                    break

            if public_ok:
                break

        if checker_exe is None:
            logger.warning("[CHECKER] Failed to build checker, using public tests only")
        else:
            solver_tiers = [
                "Implement the simplest correct solution. You may ignore time and memory limits; brute force is acceptable.",
                "Optimize moderately to handle larger inputs, but correctness is more important than performance.",
                "Implement a solution that meets the stated constraints efficiently.",
            ]

            output_feedback = ""
            solver_ok = False
            for tier_idx, tier_instruction in enumerate(solver_tiers):
                solver_feedback = output_feedback
                for attempt in range(1, output_max_iter + 1):
                    solver_prompt = build_solver_prompt(problem_desc, constraints, public_tests, tier_instruction, solver_feedback)
                    solver_response = out_llm.generate(solver_prompt)
                    llm_calls += 1
                    (code_dir / f"solver_{tier_idx + 1}_{attempt}_raw.txt").write_text(solver_response, encoding="utf-8")
                    solver_cpp = sanitize_cpp(solver_response)

                    solver_path = code_dir / f"solver_{tier_idx + 1}_{attempt}.cpp"
                    solver_path.write_text(solver_cpp, encoding="utf-8")
                    solver_exe = code_dir / f"solver_{tier_idx + 1}_{attempt}.exe"
                    solver_compile_ok, solver_log = compile_cpp(solver_path, solver_exe, include_testlib=False)
                    if not solver_compile_ok:
                        solver_feedback = f"Solver compile failed: {solver_log}"
                        (code_dir / f"solver_{tier_idx + 1}_{attempt}.log").write_text(solver_log, encoding="utf-8")
                        continue


                    failed = []
                    timeout_or_runtime = False
                    total_run = 0
                    for i, inp in enumerate(generated_inputs):
                        total_run += 1
                        input_path = tests_dir / f"gen_{i}.in"
                        output_path = tests_dir / f"gen_{i}.out"
                        # Clean trailing empty lines from input
                        cleaned_input = inp.rstrip("\n") + "\n"
                        input_path.write_text(cleaned_input, encoding="utf-8")
                        try:
                            code, out, err = run_program(solver_exe, input_text=inp, timeout=2)
                        except Exception as ex:
                            code, out, err = 1, "", str(ex)


                        if code != 0 or not out.strip():
                            timeout_or_runtime = True
                            failed.append({"id": i, "error": err or "runtime error", "input": inp})
                            break


                        output_path.write_text(out.strip() + "\n", encoding="utf-8")
                        ok, err = run_checker(checker_exe, input_path, output_path, output_path)
                        if not ok:
                            failed.append({"id": i, "error": err, "input": inp, "output": out})


                    if not failed:
                        generated_outputs = [
                            (tests_dir / f"gen_{i}.out").read_text(encoding="utf-8").strip() + "\n"
                            for i in range(len(generated_inputs))
                        ]
                        solver_ok = True
                        break


                    solver_feedback = format_solver_feedback(failed, total_run, len(generated_inputs))
                    (tests_dir / f"solver_{tier_idx + 1}_{attempt}_failed.json").write_text(solver_feedback, encoding="utf-8")
                    output_feedback = solver_feedback  # Update outer feedback for next iteration

                    if timeout_or_runtime:
                        break

                if solver_ok:
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
                        "solver_*_*_failed.json"]:
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

    tests = {
        "generated_tests": generated_tests,
        "total_tests": len(generated_tests),
        "test_results": [],
        "passed_tests": 0,
        "pass_rate": 0.0,
        "checker_exe": str(checker_exe) if checker_exe else None,
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
    }
