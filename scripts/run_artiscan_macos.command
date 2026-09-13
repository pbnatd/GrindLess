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
python -m pip install -e '.[browser]'
python -m playwright install chromium
grindless-platform

echo
echo "Artiscan will decline transcoding and stop at the black end frame automatically."
echo "The visible browser is kept for this evaluation run so you can observe it."
echo
read -r -p "Press Return to choose the inventory video..."

video_path="$(osascript -e 'POSIX path of (choose file with prompt "Choose the Genshin artifact inventory video")')"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
result_dir="$project_dir/artiscan-e2e-result/$run_id"
mkdir -p "$result_dir"

grindless-good "$video_path" \
  --artiscan-browser \
  --artiscan-headful \
  --preset mavuika \
  --save-extracted-good "$result_dir/extracted.good.json" \
  > "$result_dir/run-report.json"

python - "$result_dir/run-report.json" <<'PY'
import json
import sys

report_path = sys.argv[1]
with open(report_path, encoding="utf-8") as report_file:
    report = json.load(report_file)
performance = report["video_extraction"]["performance"]
peak_mib = performance["peak_process_tree_rss_bytes"] / (1024 * 1024)
print(f"Measured wall time: {performance['wall_time_seconds']:.3f} s")
print(f"Peak Python + Chromium RSS: {peak_mib:.1f} MiB")
print("Interaction mode: fully automated")
if not performance["complete"]:
    print("Warning: memory measurement was incomplete:", *performance["warnings"])
PY

echo "Success. GOOD and the run report are in:"
echo "$result_dir"
open "$result_dir"
