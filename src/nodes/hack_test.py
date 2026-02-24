"""Hack Test Node - Adversarial testing for solutions"""

import json
from typing import Dict, Any, List, TYPE_CHECKING
from loguru import logger
from src.llm import UnifiedLLMClient
from src.utils.json_utils import parse_json_response
from src.utils.problem_utils import extract_problem_code

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

import tempfile
import subprocess
from pathlib import Path
from src.utils.cpp_execution import run_checker, run_program, ExecutionLimits
from src.memory import MemoryClient, MemoryNamespace

MAX_HACK_RETRIES = 3


def build_hacker_prompt(problem_desc: str, constraints: Dict[str, Any], code: str, memory_advice: str = "", validator_feedback: str = "") -> str:
    constraints_json = json.dumps(constraints, indent=2)
    
    advice_section = ""
    if memory_advice:
        advice_section = f"\n=== HACKER STRATEGY ADVICE ===\n{memory_advice}\n=============================\n"

    feedback_section = ""
    if validator_feedback:
        feedback_section = f"\n=== PREVIOUS ATTEMPT REJECTED ===\n{validator_feedback}\nPlease generate DIFFERENT test inputs that strictly satisfy all constraints.\n=================================\n"
        
    return f"""You are a competitive programming hacker. Your goal is to find a test case that breaks the given solution.

Problem Description:
{problem_desc}
{advice_section}
{feedback_section}
⚠️ CONSTRAINTS (EVERY test input MUST satisfy ALL of these):
{constraints_json}

CRITICAL: If any value in your test input violates these constraints, the validator will reject it.
Focus on finding bugs WITHIN the constraint bounds, not by exceeding them.

Solution Code:
```cpp
{code}
```

ANALYSIS TASK:
1. Identify specific algorithmic bugs in the code (overflow, edge cases, boundary conditions, wrong logic paths).
2. Generate 1-5 test inputs that trigger these bugs WHILE RESPECTING ALL CONSTRAINTS.
3. For boundary cases, use values at or near the constraint limits if possible.
4. Every single value must be within the specified ranges.

INPUT FORMAT (MUST FOLLOW EXACTLY):
Each line must end with exactly one newline character.
Do not add extra blank lines.

Return ONLY valid JSON with no other text.

VALID JSON Schema:
{{
    "analysis": "<identification of bugs found in the code>",
    "hack_tests": [
        {{"input": "<complete input string including all newlines, respecting all constraints>"}}
    ]
}}

Example response (if n <= 5, k <= 3):
{{
    "analysis": "Bug: when n=2 and values are similar, the algorithm fails to handle the case correctly",
    "hack_tests": [
        {{"input": "2 1\\n1000000000 0\\n-1000000000 0\\n"}}
    ]
}}
"""


def hack_test_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Adversarial Hack Phase
    
    1. LLM analyzes code and generates "hack" test cases.
    2. Local syntax validator intercepts (retry loop ≤3 if all rejected).
    3. Run valid tests against the executable.
    4. Compute hacker_reward and update state.
    """
    def normalize_hack_input(inp: str) -> str:
        """Normalize hack test input to ensure it matches validator requirements."""
        lines = inp.split('\n')
        normalized_lines = []
        
        for line in lines:
            if line.strip() == "":
                continue
            normalized_lines.append(line.rstrip())
        
        if normalized_lines:
            return '\n'.join(normalized_lines) + '\n'
        return inp
    
    logger.info("[Node] Adversarial Hack")
    
    config = UnifiedLLMClient.build_role_config(state.get("config", {}), "hacker")
    
    code = state["solution"].get("code", "")
    exe_path = state["solution"].get("executable_path")
    problem_desc = state["problem"].get("description", "")
    constraints = state["problem"].get("constraints", {})
    hack_round = state.get("hack_round", 0) + 1
    
    if not exe_path or not Path(exe_path).exists():
        logger.error("No executable found for hack test")
        return {
            "hack_round": hack_round,
            "hack_passed": False,
            "hacker_reward": -1.0,
            "hack_failures": [{"error": "No executable"}],
        }

    # T3.1: Initialize Memory Client with correct API
    canonical = state.get("problem", {}).get("canonical", {})
    memory = MemoryClient(
        namespace=MemoryNamespace.HACK,
        config=state.get("config", {}),
        problem_desc=problem_desc,
        canonical=canonical,
    )

    # T3.1: Use keyword-only get_injection signature (no Observation object)
    advice, item_ids = memory.get_injection(
        fsm_state="HACK_GEN",
        failure_type=None,
        attempt_count=hack_round,
    )

    # Initialize LLM
    llm = UnifiedLLMClient(config)

    tests_data = state.get('tests', {})
    checker_exe = tests_data.get('checker_exe')
    validator_exe = tests_data.get('validator_exe')

    # T3.2: Inner retry loop — retry LLM if all inputs rejected by validator
    hack_tests: List[Dict] = []
    analysis = "No analysis"
    validator_feedback = ""

    for attempt in range(1, MAX_HACK_RETRIES + 1):
        prompt = build_hacker_prompt(
            problem_desc, constraints, code,
            memory_advice=advice,
            validator_feedback=validator_feedback,
        )
        response = llm.generate(prompt)

        try:
            data = parse_json_response(response)
            raw_tests = data.get("hack_tests", [])
            analysis = data.get("analysis", "No analysis")
            logger.info(f"[HACK] Attempt {attempt}: Analysis: {analysis}")
            logger.info(f"[HACK] Attempt {attempt}: Generated {len(raw_tests)} hack tests")
        except Exception as e:
            logger.warning(f"[HACK] Attempt {attempt}: Failed to parse hacker response: {e}")
            # Skip this round — don't block workflow
            return {
                "hack_round": hack_round,
                "hack_passed": True,
                "hacker_reward": 0.0,
                "hacker_memory_item_ids": item_ids,
                "execution_log": [f"Hack round {hack_round} skipped (LLM parse error)"],
            }

        if not validator_exe or not Path(validator_exe).exists():
            # No validator available — just accept all generated tests
            hack_tests = raw_tests
            break

        # Validate each input; collect rejection reasons for feedback
        valid_tests = []
        rejection_reasons = []

        for i, test in enumerate(raw_tests):
            inp = normalize_hack_input(test.get("input", ""))
            v_code, _, v_err = run_program(
                Path(validator_exe),
                input_text=inp,
                limits=ExecutionLimits.default_run(),
            )
            if v_code != 0:
                reason = v_err.strip() or f"validator exited {v_code}"
                rejection_reasons.append(f"Input {i}: {reason[:120]}")
                logger.debug(f"[HACK] Validator rejected input {i}: {reason}")
            else:
                valid_tests.append({"input": inp, "expected_output": test.get("expected_output", "")})

        if valid_tests:
            hack_tests = valid_tests
            logger.info(f"[HACK] Attempt {attempt}: {len(valid_tests)}/{len(raw_tests)} inputs passed validator")
            break
        else:
            # All rejected — feed validator reasons back to LLM for next attempt
            logger.warning(
                f"[HACK] Attempt {attempt}: All {len(raw_tests)} inputs rejected by validator — retrying"
            )
            validator_feedback = "\n".join(rejection_reasons)

    # ========== Run Valid Hack Tests ==========
    failures = []
    validated_hacks = hack_tests  # Already filtered above
    # (re-run normalization for the no-validator path)
    if not validator_exe or not Path(validator_exe).exists():
        validated_hacks = [
            {**t, "input": normalize_hack_input(t.get("input", ""))}
            for t in hack_tests
        ]

    all_rejected = len(validated_hacks) == 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        for i, test in enumerate(validated_hacks):
            inp = test.get("input", "")
            exp = test.get("expected_output", "").strip()

            try:
                res = subprocess.run(
                    [exe_path],
                    input=inp,
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                actual = res.stdout.strip()
                
                if res.returncode != 0:
                    failures.append({
                        "type": "Runtime Error",
                        "input": inp,
                        "output": res.stderr,
                        "expected": exp
                    })
                    continue
                
                if checker_exe and Path(checker_exe).exists():
                    input_file = tmp_path / f"hack_{i}.in"
                    output_file = tmp_path / f"hack_{i}.out"
                    answer_file = tmp_path / f"hack_{i}.ans"
                    
                    input_file.write_text(inp, encoding="utf-8")
                    output_file.write_text(res.stdout, encoding="utf-8")
                    answer_file.write_text(exp if exp else "", encoding="utf-8")
                    
                    chk_ok, chk_msg = run_checker(Path(checker_exe), input_file, output_file, answer_file)
                    if not chk_ok:
                        failures.append({
                            "type": "Wrong Answer (Checker)",
                            "input": inp,
                            "output": actual,
                            "expected": exp,
                            "details": chk_msg
                        })
                else:
                    if exp and actual != exp:
                        failures.append({
                            "type": "Wrong Answer",
                            "input": inp,
                            "output": actual,
                            "expected": exp
                        })
            
            except subprocess.TimeoutExpired:
                failures.append({
                    "type": "Time Limit Exceeded",
                    "input": inp,
                    "expected": exp
                })
            except Exception as e:
                failures.append({
                    "type": "System Error",
                    "input": inp,
                    "details": str(e)
                })

    # T3.3: Reward shaping (per research doc §2.3)
    # +1.0 = found WA/RE/TLE bug (hack succeeded)
    # -1.0 = all inputs rejected by validator across all retries
    #  0.0 = valid inputs, but solution passed them all
    if failures:
        hacker_reward = 1.0
    elif all_rejected:
        hacker_reward = -1.0
    else:
        hacker_reward = 0.0

    # Append validator-approved hack tests to generated_tests for regression
    new_tests = []
    for t in validated_hacks:
        if t.get("input"):
            new_tests.append({
                "input": t.get("input"),
                "expected_output": t.get("expected_output", ""),
                "type": "hack"
            })

    generated_tests = tests_data.get('generated_tests', [])
    updated_tests = dict(tests_data)
    updated_tests['generated_tests'] = generated_tests + new_tests
    updated_tests['total_tests'] = len(updated_tests['generated_tests'])

    # Persist hack tests to disk
    problem_code = extract_problem_code(state.get("raw_problem", {}))
    if problem_code:
        tests_dir = Path("data") / "generated" / problem_code / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        existing = list(tests_dir.glob("hack_*.in"))
        next_idx = 0
        if existing:
            try:
                indices = [int(p.stem.split("_")[1]) for p in existing if p.stem.count("_") == 1]
                next_idx = max(indices) + 1 if indices else 0
            except ValueError:
                next_idx = 0

        for offset, t in enumerate(new_tests):
            inp = t.get("input", "")
            exp = t.get("expected_output", "")
            input_path = tests_dir / f"hack_{next_idx + offset}.in"
            output_path = tests_dir / f"hack_{next_idx + offset}.out"
            input_path.write_text(inp.rstrip("\n") + "\n", encoding="utf-8")
            output_path.write_text(exp.rstrip("\n") + ("\n" if exp else ""), encoding="utf-8")

    if failures:
        logger.warning(f"Hack successful! Found {len(failures)} failures.")
        return {
            "hack_round": hack_round,
            "hack_passed": False,
            "hack_failures": failures,
            "hacker_reward": hacker_reward,
            "hacker_memory_item_ids": item_ids,
            "tests": updated_tests,
            "execution_log": [f"Hack round {hack_round} FAILED. Added {len(new_tests)} regression tests."],
        }
    
    logger.info(f"Hack round {hack_round} passed. Reward={hacker_reward:.1f}")
    if all_rejected:
        logger.warning(f"All hack inputs were rejected by validator across {MAX_HACK_RETRIES} retries.")
    return {
        "hack_round": hack_round,
        "hack_passed": True,
        "hack_failures": [],
        "hacker_reward": hacker_reward,
        "hacker_memory_item_ids": item_ids,
        "tests": updated_tests,
        "execution_log": [
            f"Hack round {hack_round} passed. Reward={hacker_reward:.1f}. "
            f"Added {len(new_tests)} regression tests."
        ],
    }
