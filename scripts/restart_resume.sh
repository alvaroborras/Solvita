#!/usr/bin/env bash
# Resume all incomplete benchmark configs after metadata fix.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
CONFIG="${ROOT}/config/models.yaml"
OUT_ROOT="${ROOT}/benchmark_results/20260416T055344Z"
LOG_DIR="${OUT_ROOT}/logs"
mkdir -p "${LOG_DIR}"

WORKERS=2

run_bench() {
  local label="$1"
  local mode="$2"
  local extra_flags="${3:-}"
  local out_dir="${OUT_ROOT}/${label}"
  local log="${LOG_DIR}/${label}_resume3.log"

  {
    echo ">>> [${label}] Resuming (workers=${WORKERS})..."

    for bench_args in \
      "code-contest" \
      "apps --apps-difficulty competition" \
      "aethercode"; do
      local bench="${bench_args%% *}"
      local extra_bench="${bench_args#* }"
      [ "$extra_bench" = "$bench_args" ] && extra_bench=""
      echo "    [${label}] ${bench}..."
      PYTHONPATH="${ROOT}" ${PYTHON} "${ROOT}/scripts/run_benchmark.py" \
        --bench ${bench} \
        ${extra_bench} \
        --output-dir "${out_dir}" \
        --modes ${mode} \
        --config-path "${CONFIG}" \
        --max-workers "${WORKERS}" \
        ${extra_flags} || echo "    [${label}] ${bench} FAILED."
    done

    echo ">>> [${label}] DONE."
  } > "${log}" 2>&1
}

PIDS=()
LABELS=()

launch() {
  local label="$1"; shift
  run_bench "$label" "$@" &
  PIDS+=($!)
  LABELS+=("$label")
  echo "  Launched ${label} (PID $!)"
}

echo "Launching resume jobs..."

# Config 1: single_pass — apps missing 1, aethercode missing 398
launch "1_single_pass" "single_pass"

# Config 2: baseline — apps 439/1000, aethercode 0
launch "2_baseline" "solvita_pipeline"

# Configs 3-7
launch "3_add_solver_network" "solvita_pipeline" "--solver-network"
launch "4_add_tm_hacker"      "solvita_pipeline" "--tm-hacker --no-tm-oracle"
launch "5_add_tm_oracle"      "solvita_pipeline" "--tm-oracle --no-tm-hacker"
launch "6_add_tm_both"        "solvita_pipeline" "--trainable-memory"
launch "7_full_system"        "solvita_pipeline" "--solver-network --trainable-memory"

echo ""
echo "All 7 configs launched. Logs: ${LOG_DIR}/<config>_resume3.log"
echo ""

FAILED=()
for i in "${!PIDS[@]}"; do
  pid="${PIDS[$i]}"
  label="${LABELS[$i]}"
  if wait "$pid"; then
    echo "  ✓ ${label} done."
  else
    echo "  ✗ ${label} had errors."
    FAILED+=("$label")
  fi
done

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "WARNING: ${#FAILED[@]} config(s) had errors: ${FAILED[*]}"
  exit 1
fi
echo "All configs complete."
