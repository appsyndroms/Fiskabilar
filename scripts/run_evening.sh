#!/bin/bash
set -euo pipefail
FISKABILAR_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$FISKABILAR_ROOT"
FISKABILAR_PYTHON="${FISKABILAR_PYTHON:-$FISKABILAR_ROOT/.venv/bin/python}"
if [ ! -x "$FISKABILAR_PYTHON" ]; then
  echo "Pythonmiljön saknas. Kör scripts/setup_local.py med Python 3.11 eller senare."
  exit 1
fi
mkdir -p .local/logs .local/act
export FISKABILAR_ROOT FISKABILAR_PYTHON
args=(workflow_dispatch -W .github/workflows/evening-local.yml
  --action-cache-path "$FISKABILAR_ROOT/.local/act"
  --env "FISKABILAR_ROOT=$FISKABILAR_ROOT" --env "FISKABILAR_PYTHON=$FISKABILAR_PYTHON")
act "${args[@]}" "$@" 2>&1 | tee -a .local/logs/evening.log
