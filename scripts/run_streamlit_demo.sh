#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"
VENV_PYTHON="${VENV_PYTHON:-$WORKSPACE_ROOT/.venv/bin/python}"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Python interpreter not found: $VENV_PYTHON" >&2
  echo "Set VENV_PYTHON=/path/to/venv/bin/python and run again." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
"$VENV_PYTHON" -m streamlit run streamlit_app.py
