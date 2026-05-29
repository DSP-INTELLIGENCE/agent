#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="${AGENT_VENV_DIR:-$repo_root/.venv}/bin/python"

if [ ! -x "$venv_python" ]; then
  echo "Agent venv Python not found: $venv_python" >&2
  echo "Run ./scripts/bootstrap_venv.sh first." >&2
  exit 1
fi

exec "$venv_python" "$@"
