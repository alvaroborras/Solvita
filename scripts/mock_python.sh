#!/usr/bin/env bash
# Replay a canned NDJSON event stream, simulating main.py --stream-events.
# Used by cli mock-test to render the TUI without spending real LLM tokens.
#
# Ignores all flags; just emit the events with realistic delays.

emit() {
  printf '%s\n' "$1"
  sleep "${2:-0.4}"
}

emit '{"type": "solve_start", "problem_id": "two-sum", "max_iterations": 5}' 0.2

emit '{"type": "phase_start", "phase": "abstract_phase", "label": "Abstracting Problem"}' 0.6
emit '{"type": "phase_done", "phase": "abstract_phase", "label": "Abstracting Problem", "data": {"tags": ["hashing", "data_structures"], "confidence": 0.99}}' 0.2
emit '{"type": "token_sample", "prompt_tokens": 4123, "completion_tokens": 612, "total": 4735}' 0.4

emit '{"type": "phase_start", "phase": "testgen_phase", "label": "Generating Tests"}' 0.6
emit '{"type": "phase_done", "phase": "testgen_phase", "label": "Generating Tests", "data": {"test_count": 3}}' 0.2
emit '{"type": "token_sample", "prompt_tokens": 18420, "completion_tokens": 2871, "total": 21291}' 0.4

emit '{"type": "phase_start", "phase": "solver_skill_plan", "label": "Planning Strategy"}' 0.5
emit '{"type": "phase_done", "phase": "solver_skill_plan", "label": "Planning Strategy", "data": {"algorithm": "hash_table"}}' 0.2
emit '{"type": "token_sample", "prompt_tokens": 26580, "completion_tokens": 4002, "total": 30582}' 0.4

emit '{"type": "phase_start", "phase": "codegen_phase", "label": "Generating & Testing Code"}' 1.2
emit '{"type": "phase_done", "phase": "codegen_phase", "label": "Generating & Testing Code", "data": {"iteration": 0, "compile_success": true, "passed": 3, "total": 3, "pass_rate": 1.0}}' 0.2
emit '{"type": "token_sample", "prompt_tokens": 54820, "completion_tokens": 8741, "total": 63561}' 0.4

emit '{"type": "phase_start", "phase": "hacker_phase", "label": "Adversarial Hack Testing"}' 1.5
emit '{"type": "phase_done", "phase": "hacker_phase", "label": "Adversarial Hack Testing", "data": {"hack_passed": false, "hack_round": 1, "failure_type": "WA", "failing_input_head": "200000\n1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 …", "expected_head": "199998 199999", "actual_head": "0 1", "details": "checker: indices order mismatch on monotone array"}}' 0.4
emit '{"type": "token_sample", "prompt_tokens": 92450, "completion_tokens": 13208, "total": 105658}' 0.6

emit '{"type": "phase_start", "phase": "codegen_phase", "label": "Generating & Testing Code"}' 1.2
emit '{"type": "phase_done", "phase": "codegen_phase", "label": "Generating & Testing Code", "data": {"iteration": 1, "compile_success": true, "passed": 3, "total": 4, "pass_rate": 0.75}}' 0.2
emit '{"type": "token_sample", "prompt_tokens": 124300, "completion_tokens": 17604, "total": 141904}' 0.4

emit '{"type": "phase_start", "phase": "codegen_phase", "label": "Generating & Testing Code"}' 1.0
emit '{"type": "phase_done", "phase": "codegen_phase", "label": "Generating & Testing Code", "data": {"iteration": 2, "compile_success": true, "passed": 4, "total": 4, "pass_rate": 1.0}}' 0.2
emit '{"type": "token_sample", "prompt_tokens": 162840, "completion_tokens": 21506, "total": 184346}' 0.4

emit '{"type": "phase_start", "phase": "hacker_phase", "label": "Adversarial Hack Testing"}' 1.0
emit '{"type": "phase_done", "phase": "hacker_phase", "label": "Adversarial Hack Testing", "data": {"hack_passed": true, "hack_round": 2}}' 0.2
emit '{"type": "token_sample", "prompt_tokens": 198432, "completion_tokens": 24108, "total": 222540}' 0.4

emit '{"type": "final", "status": "success", "iterations": 3, "llm_calls": 87, "passed": 4, "total": 4, "pass_rate": 1.0, "prompt_tokens": 198432, "completion_tokens": 24108}' 0.2
emit '{"type": "solution_saved", "path": "./solution.cpp"}' 0.1
