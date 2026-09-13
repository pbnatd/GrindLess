#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -x .venv/bin/grindless-linux-game ]]; then
  echo "Run scripts/run_grindless_app_linux.sh once before this check."
  exit 1
fi

exec .venv/bin/grindless-linux-game
