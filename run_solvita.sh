#!/usr/bin/env bash
# Convenience wrapper: pins python to venv and forwards all args to the CLI.
# Usage:
#   ./run_solvita.sh                                # interactive TUI
#   ./run_solvita.sh solve examples/foo.json        # direct mode
#   ./run_solvita.sh solve foo.json -n 5 -o out.cpp # with options
#
# Required env vars:
#   SOLVITA_API_KEY     LLM provider api key
#   SOLVITA_BASE_URL    (optional, defaults to value in config/models.yaml)

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${SOLVITA_API_KEY:-}" ]]; then
  echo "ERROR: SOLVITA_API_KEY is not set." >&2
  echo "  export SOLVITA_API_KEY='sk-...'" >&2
  exit 1
fi

PY="$HERE/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: venv not found at $PY. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# If first arg is "solve", inject --python into the solve subcommand
if [[ "${1:-}" == "solve" ]]; then
  shift
  exec solvita solve --python "$PY" "$@"
else
  # Interactive mode (no subcommand) does NOT accept --python; just launch.
  exec solvita "$@"
fi
