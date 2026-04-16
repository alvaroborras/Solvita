#!/usr/bin/env bash
# =============================================================
# run_all_benchmarks.sh — Full ablation study (config-level parallel)
# =============================================================
#
# Three networks under ablation:
#   - solver_network           (skill graph injection)
#   - trainable_memory:hacker  (hacker namespace memory)
#   - trainable_memory:oracle  (oracle namespace memory)
#
# Ablation design (7 configs, incremental addition):
#   1. single_pass                              — 裸模型
#   2. baseline                                 — 纯 pipeline, 所有网络关
#   3. +solver_network                          — 逐个加: solver_network
#   4. +tm:hacker                               — 逐个加: trainable_memory (仅 hacker)
#   5. +tm:oracle                               — 逐个加: trainable_memory (仅 oracle)
#   6. +tm:both                                 — trainable_memory (hacker + oracle)
#   7. full system                              — solver_network + trainable_memory
#
# Datasets:
#   code-contest  — full test set (165 problems)
#   apps          — competition difficulty only (~1000 problems)
#   aethercode    — full test set (~460 problems)
#
# Execution strategy:
#   - All 7 configs run in parallel (background jobs)
#   - Each config runs its 3 datasets sequentially
#   - Per-config workers share the API rate limit budget
#   - Total sustained API load ≈ parallel_configs × workers_per_config
#
# Usage:
#   bash scripts/run_all_benchmarks.sh [--max-workers N]
#
# Results: benchmark_results/<timestamp>/<config>/<dataset>/
# =============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
CONFIG="${ROOT}/config/models.yaml"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_ROOT="${ROOT}/benchmark_results/${TS}"
LOG_DIR="${OUT_ROOT}/logs"
mkdir -p "${LOG_DIR}"

# Concurrency design (CloudGPT rate limit: 8 sustained = safe ceiling):
#   7 configs in parallel, each with WORKERS_PER_CONFIG workers
#   Total concurrent API calls ≈ 7 × WORKERS_PER_CONFIG
#   Config 1 (single_pass) is lightweight (1 LLM call/problem) — 1 worker enough
#   Configs 2-7 (pipeline) are heavy (~100+ LLM calls/problem)
#   With 7 pipeline configs × 1 worker each = 7 concurrent workflows
#   Each workflow makes sequential LLM calls, so actual concurrency is manageable.
WORKERS_PER_CONFIG=2
MAX_WORKERS_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --max-workers) MAX_WORKERS_OVERRIDE="$2"; shift 2 ;;
    *)             echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ -n "$MAX_WORKERS_OVERRIDE" ]]; then
  WORKERS_PER_CONFIG="$MAX_WORKERS_OVERRIDE"
fi

echo "=========================================="
echo "Ablation study: ${TS}"
echo "Output root:    ${OUT_ROOT}"
echo "Workers/config: ${WORKERS_PER_CONFIG}"
echo "Parallel configs: 7 (all concurrent)"
echo "Datasets:       code-contest (full), apps (competition), aethercode (full)"
echo ""
echo "Configs:"
echo "  1. single_pass              (裸模型)"
echo "  2. baseline                 (纯 pipeline)"
echo "  3. +solver_network          (消融)"
echo "  4. +tm:hacker               (消融)"
echo "  5. +tm:oracle               (消融)"
echo "  6. +tm:hacker+oracle        (消融)"
echo "  7. full system              (all networks)"
echo "=========================================="

# ---------------------------------------------------------------
# run_bench: runs one config across all 3 datasets (sequentially)
# Called as a background job — one per config.
# ---------------------------------------------------------------
run_bench() {
  local label="$1"
  local mode="$2"
  local max_workers="$3"
  local extra_flags="${4:-}"
  local out_dir="${OUT_ROOT}/${label}"
  local log="${LOG_DIR}/${label}.log"
  local failed=0

  {
    echo ">>> [${label}] Starting (workers=${max_workers})..."

    # code-contest: full test set
    echo "    [${label}] code-contest (full)..."
    if ! PYTHONPATH="${ROOT}" ${PYTHON} "${ROOT}/scripts/run_benchmark.py" \
      --bench code-contest \
      --output-dir "${out_dir}" \
      --modes ${mode} \
      --config-path "${CONFIG}" \
      --max-workers "${max_workers}" \
      ${extra_flags}; then
      echo "    [${label}] code-contest FAILED."
      failed=1
    fi

    # apps: competition difficulty only
    echo "    [${label}] apps (competition)..."
    if ! PYTHONPATH="${ROOT}" ${PYTHON} "${ROOT}/scripts/run_benchmark.py" \
      --bench apps \
      --apps-difficulty competition \
      --output-dir "${out_dir}" \
      --modes ${mode} \
      --config-path "${CONFIG}" \
      --max-workers "${max_workers}" \
      ${extra_flags}; then
      echo "    [${label}] apps FAILED."
      failed=1
    fi

    # aethercode: full test set
    echo "    [${label}] aethercode (full)..."
    if ! PYTHONPATH="${ROOT}" ${PYTHON} "${ROOT}/scripts/run_benchmark.py" \
      --bench aethercode \
      --output-dir "${out_dir}" \
      --modes ${mode} \
      --config-path "${CONFIG}" \
      --max-workers "${max_workers}" \
      ${extra_flags}; then
      echo "    [${label}] aethercode FAILED."
      failed=1
    fi

    if [[ $failed -eq 0 ]]; then
      echo ">>> [${label}] DONE."
    else
      echo ">>> [${label}] DONE (with errors)."
    fi

    return $failed
  } > "${log}" 2>&1
}

# ---------------------------------------------------------------
# Launch all 7 configs in parallel
# ---------------------------------------------------------------
PIDS=()
LABELS=()

launch() {
  local label="$1"; shift
  run_bench "$label" "$@" &
  PIDS+=($!)
  LABELS+=("$label")
  echo "  Launched ${label} (PID $!)"
}

echo ""
echo "Pre-warming benchmark manifests (avoid parallel write races)..."
PYTHONPATH="${ROOT}" ${PYTHON} -c "
from scripts.run_benchmark import _build_payloads_from_hf, _write_bench_payload_manifest
from pathlib import Path
bench_root = Path('${ROOT}/benchmark/manifests')
for bench, kw in [('code-contest', {}), ('apps', {'apps_difficulty': 'competition'}), ('aethercode', {})]:
    print(f'  Building {bench}...')
    payloads = _build_payloads_from_hf(bench, limit=None, **kw)
    _write_bench_payload_manifest(bench_name=bench, payloads=payloads, bench_root=bench_root)
    print(f'  {bench}: {len(payloads)} problems cached.')
"
echo "Manifests ready."

echo ""
echo "Launching all configs..."

# 1. single_pass — lightweight, give it more workers
launch "1_single_pass" "single_pass" "${WORKERS_PER_CONFIG}"

# 2-7: pipeline configs
launch "2_baseline"          "solvita_pipeline" "${WORKERS_PER_CONFIG}"
launch "3_add_solver_network" "solvita_pipeline" "${WORKERS_PER_CONFIG}" "--solver-network"
launch "4_add_tm_hacker"     "solvita_pipeline" "${WORKERS_PER_CONFIG}" "--tm-hacker --no-tm-oracle"
launch "5_add_tm_oracle"     "solvita_pipeline" "${WORKERS_PER_CONFIG}" "--tm-oracle --no-tm-hacker"
launch "6_add_tm_both"       "solvita_pipeline" "${WORKERS_PER_CONFIG}" "--trainable-memory"
launch "7_full_system"       "solvita_pipeline" "${WORKERS_PER_CONFIG}" "--solver-network --trainable-memory"

echo ""
echo "All 7 configs launched. Waiting for completion..."
echo "Per-config logs: ${LOG_DIR}/<config>.log"
echo ""

# ---------------------------------------------------------------
# Wait for all and collect exit codes
# ---------------------------------------------------------------
FAILED_CONFIGS=()
for i in "${!PIDS[@]}"; do
  pid="${PIDS[$i]}"
  label="${LABELS[$i]}"
  if wait "$pid"; then
    echo "  ✓ ${label} completed successfully."
  else
    echo "  ✗ ${label} completed with errors. See ${LOG_DIR}/${label}.log"
    FAILED_CONFIGS+=("$label")
  fi
done

echo ""
echo "=========================================="
echo "Ablation study complete."
echo "Results: ${OUT_ROOT}"
echo ""
echo "Ablation analysis:"
echo "  1 vs 2                  → pipeline gain over raw model"
echo "  2 vs 3                  → solver_network Δ"
echo "  2 vs 4                  → tm:hacker Δ"
echo "  2 vs 5                  → tm:oracle Δ"
echo "  2 vs 6                  → tm:hacker+oracle Δ  (vs 4+5 → interaction)"
echo "  2 vs 7                  → full system Δ       (vs 3+6 → interaction)"
echo "=========================================="

if [[ ${#FAILED_CONFIGS[@]} -gt 0 ]]; then
  echo ""
  echo "WARNING: ${#FAILED_CONFIGS[@]} config(s) had errors:"
  for cfg in "${FAILED_CONFIGS[@]}"; do
    echo "  - ${cfg}"
  done
  exit 1
fi
