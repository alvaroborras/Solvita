#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION_NAME="${1:-hacker_train_p12}"
WORKERS="${WORKERS:-12}"
export WORKERS

if [[ $# -ge 2 ]]; then
  exec "${SCRIPT_DIR}/run_hacker_train_screen.sh" "${SESSION_NAME}" "$2"
fi

exec "${SCRIPT_DIR}/run_hacker_train_screen.sh" "${SESSION_NAME}"
