#!/usr/bin/env bash
# Run LabDesk automated tests (offscreen Qt; no display needed).
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

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

if ! python -c "import pytest" 2>/dev/null; then
  echo "Installing pytest into the active environment…"
  if command -v uv >/dev/null 2>&1; then
    uv pip install -r requirements-dev.txt
  else
    python -m pip install -r requirements-dev.txt
  fi
fi

# Prefer a built labdesk_core when present (URL / error parsing tests).
# PYTHONPATH=src alone can make the Rust crate look like a namespace package —
# require a real extension attribute before skipping the maturin build.
if ! python -c "import labdesk_core; assert hasattr(labdesk_core, 'forge_feature_matrix') or hasattr(labdesk_core, 'repo_status')" 2>/dev/null; then
  if command -v maturin >/dev/null 2>&1; then
    echo "Building labdesk_core for tests…"
    (cd "$ROOT/src/labdesk_core" && maturin develop --uv)
  else
    echo "WARNING: labdesk_core extension not importable; core-dependent tests will skip."
  fi
fi

exec python -m pytest "$@"
