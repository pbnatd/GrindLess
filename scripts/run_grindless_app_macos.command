#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This launcher is for macOS. Use the README commands on another OS." >&2
  exit 2
fi

launcher_dir="$(cd "$(dirname "$0")" && pwd)"
project_dir="$(cd "$launcher_dir/.." && pwd)"
cd "$project_dir"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.12 or newer is required. Install it from python.org first." >&2
  exit 2
fi

python3 - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit(
        f"Python 3.12 or newer is required; found {sys.version.split()[0]}"
    )
PY

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -e '.[app,browser]'
python -m playwright install chromium

if api_key="$(security find-generic-password -a "$USER" -s "GrindLess OpenAI API" -w 2>/dev/null)"; then
  export OPENAI_API_KEY="$api_key"
  unset api_key
  echo "GPT API key loaded from macOS Keychain."
else
  echo "GPT API key is not configured; offline mode remains available."
fi

GRINDLESS_PORT="$(python - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.bind(("127.0.0.1", 0))
    print(probe.getsockname()[1])
PY
)"
export GRINDLESS_PORT

echo "Starting GrindLess at http://127.0.0.1:${GRINDLESS_PORT}"
echo "Keep this window open while using the application."
echo "Press Control-C here to stop it."
python -m grindless.web_app
