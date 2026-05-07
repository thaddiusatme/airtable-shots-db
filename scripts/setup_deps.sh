#!/usr/bin/env bash
# Portable dependency installer.
#
# Installs Python deps into a vendored `.deps/` directory inside the repo.
# Unlike a venv, `.deps/` has NO hardcoded interpreter paths in shebangs,
# so the entire repo folder can be moved between locations (e.g. across
# external drives) and `scripts/run.sh` will keep working — as long as the
# system Python minor version stays the same.
#
# Usage:
#   ./scripts/setup_deps.sh          # install runtime deps
#   ./scripts/setup_deps.sh --dev    # install runtime + test deps

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

REQ="requirements.txt"
if [[ "${1:-}" == "--dev" ]]; then
  REQ="requirements-dev.txt"
fi

echo "Installing $REQ into $HERE/.deps ..."
python3 -m pip install --upgrade --target .deps -r "$REQ"
echo "Done. Use ./scripts/run.sh <module-or-script> to invoke Python with the vendored deps."
