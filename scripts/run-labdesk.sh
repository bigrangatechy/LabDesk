#!/usr/bin/env bash
# Build core (if needed) and launch LabDesk UI from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
fi

if [[ -f "$HOME/.local/bin/env" ]]; then
  # shellcheck source=/dev/null
  source "$HOME/.local/bin/env"
fi

cd "$ROOT/src/labdesk_core"
maturin develop --uv
cd "$ROOT"
exec env PYTHONPATH=src python -m labdesk_ui.main
