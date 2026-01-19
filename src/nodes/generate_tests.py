"""Generate Tests Node - Create test cases for the problem"""

from typing import Dict, Any, List, Optional, Tuple
import json
import re
from pathlib import Path
import subprocess
from loguru import logger
from src.graph.state import SolvitaState, TestData
from src.llm import UnifiedLLMClient


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
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response content: {cleaned[:200]}...")
        raise


def extract_problem_code(raw_problem: Dict[str, Any]) -> Optional[str]:
    '''
    正则提取题号，用于AC解的路径拼接
    '''
    metadata = raw_problem.get("_metadata", {})
    problem_id = metadata.get("problem_id", "")
    match = re.match(r"^(\d+_[A-Z])", problem_id)
    if match:
        return match.group(1)
    return None


def safe_problem_dir_name(raw_problem: Dict[str, Any]) -> str:
    '''
    生成安全目录名 data/generated/{problem_id}
    '''
    metadata = raw_problem.get("_metadata", {})
    problem_id = metadata.get("problem_id", "unknown")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", problem_id).strip("_")
    return safe or "unknown"


def compile_cpp(source_path: Path, exe_path: Path) -> Tuple[bool, str]:
    '''
    编译cpp程序(generator/validator/checker/AC解)
    '''
    result = subprocess.run(
        ["g++", "-std=c++17", "-O2", str(source_path), "-o", str(exe_path)],
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output


def run_program(exe_path: Path, input_text: Optional[str] = None, args: Optional[List[str]] = None, timeout: int = 2) -> Tuple[int, str, str]:
    '''
    统一运行可执行文件 支持stdin与argv参数
    '''
    cmd = [str(exe_path)]
    if args:
        cmd.extend(args)
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def build_generator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    '''
    生成generator程序的prompt
    '''
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    return f"""You are a generator agent. Write a C++17 program that outputs exactly one valid test case to stdout.
The program must accept a single integer seed as argv[1] and must not print any extra text.
Use the seed to vary random choices and produce diverse valid inputs.

Problem Description:
{problem_desc}

Constraints:
{json.dumps(constraints, indent=2)}

Public Tests:
{json.dumps(public_tests, indent=2)}
{feedback_block}
Return ONLY valid JSON:
{{
  "generator_cpp": "..."
}}
"""


def build_validator_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    '''
    生成validator程序的prompt
    '''
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    return f"""You are a validator agent. Write a C++17 program that reads one test case from stdin and validates it.
Exit 0 if valid, otherwise return non-zero and write a short error to stderr.
Do not print anything on success.

Problem Description:
{problem_desc}

Constraints:
{json.dumps(constraints, indent=2)}

Public Tests:
{json.dumps(public_tests, indent=2)}
{feedback_block}
Return ONLY valid JSON:
{{
  "validator_cpp": "..."
}}
"""


def build_checker_prompt(problem_desc: str, constraints: Dict[str, Any], public_tests: List[Dict[str, Any]], feedback: str) -> str:
    '''
    生成checker程序的prompt
    '''
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
Return ONLY valid JSON:
{{
  "is_multi_solution": false,
  "checker_cpp": "..."
}}
"""


def build_outputs_prompt(problem_desc: str, inputs: List[str], feedback: str) -> str:
    '''
    LLM-1输出生成prompt
    '''
    feedback_block = f"\nPrevious attempt issues:\n{feedback}\n" if feedback else ""
    items = [{"id": i, "input": inp} for i, inp in enumerate(inputs)]
    return f"""You are an output agent. For each input, produce the correct output for the problem.
Return ONLY valid JSON with outputs in the same order.

Problem Description:
{problem_desc}

Inputs:
{json.dumps(items, indent=2)}
{feedback_block}
Return ONLY valid JSON:
{{
  "outputs": [
    {{"id": 0, "output": "..."}}
  ]
}}
"""


def run_checker(checker_exe: Path, input_path: Path, output_path: Path, timeout: int = 2) -> Tuple[bool, str]:
    '''
    调用checker验证输出的合法性
    '''
    code, _, err = run_program(checker_exe, args=[str(input_path), str(output_path)], timeout=timeout)
    return code == 0, err


def generate_tests_node(state: SolvitaState) -> Dict[str, Any]:
    logger.info("[Node] Generating test cases")

    llm = UnifiedLLMClient(state["config"])
    raw_problem = state.get("raw_problem", {})
    problem_desc = state["problem"].get("description", "")
    public_tests = state["problem"].get("public_tests", [])
    constraints = state["problem"].get("constraints", {})

    llm_calls = 0
    max_iter = 3
    target_count = 10

    problem_code = extract_problem_code(raw_problem)
    problem_dir = safe_problem_dir_name(raw_problem)
    generated_root = Path("data") / "generated" / (problem_code or problem_dir)
    code_dir = generated_root / "code"
    tests_dir = generated_root / "tests"
    code_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

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
        gen_response = llm.generate(gen_prompt)
        llm_calls += 1
        try:
            gen_data = parse_json_response(gen_response)
            generator_cpp = gen_data.get("generator_cpp", "")
        except Exception:
            gen_feedback = "Invalid JSON for generator"
            continue

        gen_path = code_dir / f"generator_{attempt}.cpp"
        gen_path.write_text(generator_cpp, encoding="utf-8")
        gen_exe = code_dir / f"generator_{attempt}.exe"
        gen_ok, gen_log = compile_cpp(gen_path, gen_exe)
        if not gen_ok:
            gen_feedback = f"Generator compile failed: {gen_log}"
            continue

        val_prompt = build_validator_prompt(problem_desc, constraints, public_tests, val_feedback)
        val_response = llm.generate(val_prompt)
        llm_calls += 1
        try:
            val_data = parse_json_response(val_response)
            validator_cpp = val_data.get("validator_cpp", "")
        except Exception:
            val_feedback = "Invalid JSON for validator"
            continue

        val_path = code_dir / f"validator_{attempt}.cpp"
        val_path.write_text(validator_cpp, encoding="utf-8")
        val_exe = code_dir / f"validator_{attempt}.exe"
        val_ok, val_log = compile_cpp(val_path, val_exe)
        if not val_ok:
            val_feedback = f"Validator compile failed: {val_log}"
            continue

        generated_inputs = []
        attempts = 0
        max_attempts = target_count * 5
        while len(generated_inputs) < target_count and attempts < max_attempts:
            seed = str(1000 + attempts)
            code, out, err = run_program(gen_exe, args=[seed], timeout=2)
            attempts += 1
            if code != 0:
                gen_feedback = f"Generator runtime error: {err}"
                continue
            if not out.strip():
                gen_feedback = "Generator produced empty output"
                continue
            v_code, _, v_err = run_program(val_exe, input_text=out, timeout=2)
            if v_code != 0:
                val_feedback = f"Validator rejected input: {v_err}"
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
        ac_ok, ac_log = compile_cpp(ac_path, ac_exe)
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
            checker_response = llm.generate(checker_prompt)
            llm_calls += 1
            try:
                checker_data = parse_json_response(checker_response)
                checker_cpp = checker_data.get("checker_cpp", "")
            except Exception:
                checker_feedback = "Invalid JSON for checker"
                continue

            checker_path = code_dir / f"checker_{attempt}.cpp"
            checker_path.write_text(checker_cpp, encoding="utf-8")
            checker_exe = code_dir / f"checker_{attempt}.exe"
            checker_ok, checker_log = compile_cpp(checker_path, checker_exe)
            if not checker_ok:
                checker_feedback = f"Checker compile failed: {checker_log}"
                continue

            public_ok = True
            for i, pt in enumerate(public_tests):
                input_path = tests_dir / f"public_{i}.in"
                output_path = tests_dir / f"public_{i}.out"
                input_path.write_text(pt.get("input", ""), encoding="utf-8")
                output_path.write_text(pt.get("output", ""), encoding="utf-8")
                ok, err = run_checker(checker_exe, input_path, output_path)
                if not ok:
                    public_ok = False
                    checker_feedback = f"Public test {i} failed: {err}"
                    break

            if public_ok:
                break

        if checker_exe is None:
            logger.warning("[CHECKER] Failed to build checker, using public tests only")
        else:
            output_map = {}
            output_feedback = ""
            for attempt in range(1, max_iter + 1):
                output_prompt = build_outputs_prompt(problem_desc, generated_inputs, output_feedback)
                output_response = llm.generate(output_prompt)
                llm_calls += 1
                try:
                    output_data = parse_json_response(output_response)
                except Exception:
                    output_feedback = "Invalid JSON for outputs"
                    continue

                outputs = output_data.get("outputs", [])
                output_map = {item.get("id"): item.get("output", "") for item in outputs}
                missing = [i for i in range(len(generated_inputs)) if i not in output_map]
                if missing:
                    output_feedback = f"Missing outputs for ids: {missing}"
                    continue

                failed = []
                for i, inp in enumerate(generated_inputs):
                    input_path = tests_dir / f"gen_{i}.in"
                    output_path = tests_dir / f"gen_{i}.out"
                    input_path.write_text(inp, encoding="utf-8")
                    output_path.write_text(output_map[i], encoding="utf-8")
                    ok, err = run_checker(checker_exe, input_path, output_path)
                    if not ok:
                        failed.append({"id": i, "error": err, "input": inp})

                if not failed:
                    generated_outputs = [output_map[i].strip() + "\n" for i in range(len(generated_inputs))]
                    break

                output_feedback = json.dumps(failed, indent=2)

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

    tests = TestData(
        generated_tests=generated_tests,
        total_tests=len(generated_tests),
        test_results=[],
        passed_tests=0,
        pass_rate=0.0,
    )

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
