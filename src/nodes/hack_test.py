import json
from typing import Dict, Any, List, TYPE_CHECKING
from loguru import logger
from src.llm import UnifiedLLMClient
from src.utils.problem_utils import extract_problem_code
from src.hacker.runtime import execute_hack_candidate

if TYPE_CHECKING:
    from src.graph.state import SolvitaState

import tempfile
from pathlib import Path
from src.utils.cpp_execution import run_checker, run_program, ExecutionLimits
from src.utils.verdict import evaluate_verdict, VerdictStatus, FailureType
from src.memory import MemoryClient, MemoryNamespace
from src.nodes.code_analyst import run_code_analyst
from src.nodes.cascading_router import cascading_execution_router

# Hacker System Architectures dictates fallback up to max 3 times for Router. 
# Analyst handles its own 5-round logic.
MAX_ROUTER_RETRIES = 3


def normalize_hack_input(inp: str) -> str:
    lines = inp.split('\n')
    normalized = [line.rstrip() for line in lines if line.strip() != ""]
    if normalized:
        return '\n'.join(normalized) + '\n'
    return inp


def extract_generation_failure_metadata(routing_log: List[str]) -> Dict[str, str]:
    for entry in reversed(routing_log):
        if entry.startswith("ROUTER_META:"):
            payload = entry.split(":", 1)[1].strip()
            try:
                data = json.loads(payload)
            except Exception:
                break
            return {
                "failure_kind": str(data.get("failure_kind", "")),
                "failure_reason": str(data.get("failure_reason", "")),
            }
    return {"failure_kind": "", "failure_reason": ""}


def generate_hack_candidate(state: "SolvitaState") -> Dict[str, Any]:
    config = UnifiedLLMClient.build_role_config(state.get("config", {}), "hacker")
    hack_round = state.get("hack_round", 0) + 1

    canonical = state.get("problem", {}).get("canonical", {})
    memory = MemoryClient(
        namespace=MemoryNamespace.HACK,
        config=state.get("config", {}),
        problem_desc=state.get("problem", {}).get("description", ""),
        canonical=canonical,
    )

    advice, item_ids = memory.get_injection(
        fsm_state="HACK_GEN",
        failure_type=None,
        attempt_count=hack_round,
    )

    llm = UnifiedLLMClient(config)
    analyst_report = run_code_analyst(state, llm, max_rounds=5, memory_advice=advice)

    logger.info("[Hack Node] Handing over to Cascading Router...")
    route_used, generated_input, routing_log = cascading_execution_router(
        state,
        llm,
        analyst_report,
        max_retries=MAX_ROUTER_RETRIES,
        memory_advice=advice,
    )

    full_execution_log = ["--- Router Execution Log ---"] + routing_log
    compile_failures = sum(1 for entry in routing_log if "Compilation Failed" in entry)

    if route_used == "failed" or not generated_input:
        failure_meta = extract_generation_failure_metadata(routing_log)
        structured_rejections = [
            {"stage": entry.split(":")[0].strip(), "reason": entry.split(":", 1)[-1].strip()}
            for entry in routing_log if "failed" in entry.lower() or "fail" in entry.lower()
        ] or [{"stage": "all", "reason": "All cascading generations failed validation."}]
        full_execution_log.append("Hacker Node: All generation sequences failed.")
        return {
            "hack_round": hack_round,
            "generated_input": "",
            "generator_route_used": route_used,
            "generator_failure_kind": failure_meta["failure_kind"],
            "generator_failure_reason": failure_meta["failure_reason"],
            "hacker_memory_item_ids": item_ids,
            "analyst_report": analyst_report,
            "execution_log": full_execution_log,
            "compile_failures": compile_failures,
            "validator_rejection_reasons": structured_rejections,
        }

    return {
        "hack_round": hack_round,
        "generated_input": normalize_hack_input(generated_input),
        "generator_route_used": route_used,
        "generator_failure_kind": "",
        "generator_failure_reason": "",
        "hacker_memory_item_ids": item_ids,
        "analyst_report": analyst_report,
        "execution_log": full_execution_log,
        "compile_failures": compile_failures,
        "validator_rejection_reasons": [],
    }

def hack_test_node(state: "SolvitaState") -> Dict[str, Any]:
    """
    Adversarial Hack Phase (v2 CodeHacker)
    
    1. Code Analyst analyzes source code and generates a Vulnerability Report (JSON).
    2. Cascading Router acts on the report (Anti-Hash -> Semantic -> Stress).
    3. Runs the finalized valid hack input against the target.
    4. Evaluates Verification/Sandbox Signals.
    5. Returns updated state dictionary conforming to T3.2 state contract.
    """
    logger.info("[Node] Adversarial Hack (CodeHacker Phase II)")
    
    exe_path = state.get("solution", {}).get("executable_path")
    hack_round = state.get("hack_round", 0) + 1
    
    if not exe_path or not Path(exe_path).exists():
        logger.error("No executable found for hack test")
        return {
            "hack_round": hack_round,
            "hack_passed": False,
            "hacker_reward": -1.0,
            "hack_failures": [{"error": "No executable"}],
        }

    candidate = generate_hack_candidate(state)
    if candidate["generator_route_used"] == "failed" or not candidate["generated_input"]:
        return {
            "hack_round": candidate["hack_round"],
            "hack_passed": True,
            "hacker_reward": -1.0,
            "hacker_memory_item_ids": candidate["hacker_memory_item_ids"],
            "hack_failures": [],
            "hack_result": "GEN_FAILED",
            "generator_route_used": candidate["generator_route_used"],
            "hack_failure_type": "NONE",
            "generator_failure_kind": candidate["generator_failure_kind"],
            "generator_failure_reason": candidate["generator_failure_reason"],
            "analyst_report": candidate["analyst_report"],
            "execution_log": candidate["execution_log"],
            "validator_rejection_reasons": candidate["validator_rejection_reasons"],
        }
    
    tests_data = state.get('tests', {})
    checker_exe = tests_data.get('checker_exe')
    executed = execute_hack_candidate(
        exe_path=Path(exe_path),
        generated_input=candidate["generated_input"],
        expected_output="",
        checker_exe=Path(checker_exe) if checker_exe and Path(checker_exe).exists() else None,
        run_program_fn=run_program,
        run_checker_fn=run_checker,
        evaluate_verdict_fn=evaluate_verdict,
    )
    failures = executed["hack_failures"]
    sandbox_verdicts = executed["sandbox_verdicts"]
    compile_failures = candidate["compile_failures"] + executed.get("compile_failures", 0)
    # hacker_reward is intentionally left as a sentinel 0.0 here.
    # settle_hacker_memory (T4.2) is the sole reward computation and writeback entry point.
    hacker_reward = 0.0

    # Only broken hack inputs become regression tests for the next repair round.
    new_tests = []
    if failures:
        new_tests.append({
            "input": candidate["generated_input"],
            "expected_output": "",
            "type": "hack"
        })

    generated_tests = tests_data.get('generated_tests', [])
    updated_tests = dict(tests_data)
    if new_tests:
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

    # Derive the dominant failure type for state contract
    primary_failure_type = "NONE"
    hack_result = "SAFE"
    if failures:
        hack_result = "BREAK"
        primary_failure_type = failures[0].get("type", "NONE")

    if failures:
        logger.warning(f"Hack successful! Found {len(failures)} failures.")
        return {
            "hack_round": hack_round,
            "hack_passed": False,
            "hack_failures": failures,
            "hacker_reward": hacker_reward,
            "hacker_memory_item_ids": candidate["hacker_memory_item_ids"],
            "hack_result": hack_result,
            "generator_route_used": candidate["generator_route_used"],
            "hack_failure_type": primary_failure_type,
            "generator_failure_kind": candidate["generator_failure_kind"],
            "generator_failure_reason": candidate["generator_failure_reason"],
            "analyst_report": candidate["analyst_report"],
            "validator_rejection_reasons": candidate["validator_rejection_reasons"],
            "sandbox_verdicts": sandbox_verdicts,
            "compile_failures": compile_failures,
            "tests": updated_tests,
            "execution_log": candidate["execution_log"] + [f"Hack FAILED (Found {len(failures)} bugs). Pending reward settlement."],
        }
    
    logger.info(f"Hack round {hack_round} target passed.")
    return {
        "hack_round": hack_round,
        "hack_passed": True,
        "hack_failures": [],
        "hacker_reward": hacker_reward,
        "hacker_memory_item_ids": candidate["hacker_memory_item_ids"],
        "hack_result": "SAFE",
        "generator_route_used": candidate["generator_route_used"],
        "hack_failure_type": "NONE",
        "generator_failure_kind": candidate["generator_failure_kind"],
        "generator_failure_reason": candidate["generator_failure_reason"],
        "analyst_report": candidate["analyst_report"],
        "validator_rejection_reasons": candidate["validator_rejection_reasons"],
        "sandbox_verdicts": sandbox_verdicts,
        "compile_failures": compile_failures,
        "tests": updated_tests,
        "execution_log": candidate["execution_log"] + [f"Hack round {hack_round} target passed. Pending reward settlement."],
    }
