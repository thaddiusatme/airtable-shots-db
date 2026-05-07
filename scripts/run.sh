#!/usr/bin/env bash
# Portable Python launcher.
#
# Runs `python3` with PYTHONPATH set to the vendored `.deps/` directory and
# the repo root, so imports work regardless of where the repo lives on disk.
#
# Examples:
#   ./scripts/run.sh -m pytest tests/
#   ./scripts/run.sh import_watch_later.py --fetch-transcripts
#   ./scripts/run.sh -m publisher --capture-dir captures/VIDEO_ID_*/ ...

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$HERE/.deps" ]]; then
  echo "Error: $HERE/.deps not found. Run ./scripts/setup_deps.sh first." >&2
  exit 1
fi

export PYTHONPATH="$HERE:$HERE/.deps${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$@"
