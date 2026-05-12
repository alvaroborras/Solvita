#!/usr/bin/env bash
# Replay a canned NDJSON event stream, simulating main.py --stream-events.
# Used by cli mock-test to render the TUI without spending real LLM tokens.
#
# Ignore all flags; just emit the events with realistic delays.

EOL=$'\n'

emit() {
  printf '%s\n' "$1"
  sleep "${2:-0.4}"
}

emit '{"type": "solve_start", "problem_id": "two-sum", "max_iterations": 5}' 0.2
emit '{"type": "phase_start", "phase": "abstract_phase", "label": "Abstracting Problem"}' 0.6
emit '{"type": "phase_done", "phase": "abstract_phase", "label": "Abstracting Problem", "data": {"tags": ["hashing", "data_structures"], "confidence": 0.99}}' 0.4
emit '{"type": "phase_start", "phase": "testgen_phase", "label": "Generating Tests"}' 0.6
emit '{"type": "phase_done", "phase": "testgen_phase", "label": "Generating Tests", "data": {"test_count": 3}}' 0.4
emit '{"type": "phase_start", "phase": "solver_skill_plan", "label": "Planning Strategy"}' 0.5
emit '{"type": "phase_done", "phase": "solver_skill_plan", "label": "Planning Strategy", "data": {"algorithm": "hash_table"}}' 0.4
emit '{"type": "phase_start", "phase": "codegen_phase", "label": "Generating & Testing Code"}' 1.2
emit '{"type": "phase_done", "phase": "codegen_phase", "label": "Generating & Testing Code", "data": {"iteration": 0, "compile_success": true, "passed": 3, "total": 3, "pass_rate": 1.0}}' 0.5
emit '{"type": "phase_start", "phase": "hacker_phase", "label": "Adversarial Hack Testing"}' 1.5
emit '{"type": "phase_done", "phase": "hacker_phase", "label": "Adversarial Hack Testing", "data": {"hack_passed": false, "hack_round": 1}}' 0.6
emit '{"type": "phase_start", "phase": "codegen_phase", "label": "Generating & Testing Code"}' 1.2
emit '{"type": "phase_done", "phase": "codegen_phase", "label": "Generating & Testing Code", "data": {"iteration": 1, "compile_success": true, "passed": 3, "total": 4, "pass_rate": 0.75}}' 0.4
emit '{"type": "phase_start", "phase": "codegen_phase", "label": "Generating & Testing Code"}' 1.0
emit '{"type": "phase_done", "phase": "codegen_phase", "label": "Generating & Testing Code", "data": {"iteration": 2, "compile_success": true, "passed": 4, "total": 4, "pass_rate": 1.0}}' 0.4
emit '{"type": "phase_start", "phase": "hacker_phase", "label": "Adversarial Hack Testing"}' 1.0
emit '{"type": "phase_done", "phase": "hacker_phase", "label": "Adversarial Hack Testing", "data": {"hack_passed": true, "hack_round": 2}}' 0.4
emit '{"type": "final", "status": "success", "iterations": 3, "llm_calls": 87, "passed": 4, "total": 4, "pass_rate": 1.0, "prompt_tokens": 198432, "completion_tokens": 24108}' 0.2
emit '{"type": "solution_saved", "path": "/Data/tanh/solvita/solution.cpp"}' 0.1
