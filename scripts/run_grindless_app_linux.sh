#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This launcher is only for Linux."
  exit 1
fi

PYTHON_BIN=""
for candidate in python3.13 python3.12; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.12 or 3.13 is required. Install it and run this launcher again."
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e '.[app,browser,game]'
.venv/bin/python -m playwright install chromium

echo "Opening GrindLess at http://127.0.0.1:8765"
echo "Keep this terminal open. Press Control-C to stop the application."
exec .venv/bin/grindless-app
