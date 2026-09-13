#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper is for macOS. On Windows or Linux, set OPENAI_API_KEY in the environment." >&2
  exit 2
fi

echo "Enter an OpenAI Platform API key for the local GrindLess demo."
echo "The key will be stored in your macOS Keychain, not in the project files."
read -r -s -p "API key: " api_key
echo

if [[ -z "$api_key" ]]; then
  echo "No key entered; nothing changed." >&2
  exit 2
fi

security add-generic-password \
  -U \
  -a "$USER" \
  -s "GrindLess OpenAI API" \
  -w "$api_key" >/dev/null
unset api_key

echo "Saved. Restart GrindLess to enable the GPT API backend."
