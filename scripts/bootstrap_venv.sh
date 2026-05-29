#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${AGENT_VENV_DIR:-$repo_root/.venv}"
python_bin="${AGENT_PYTHON:-python3}"

if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python interpreter not found: $python_bin" >&2
  exit 1
fi

if [ ! -d "$venv_dir" ]; then
  "$python_bin" -m venv "$venv_dir"
fi

"$venv_dir/bin/python" -m pip install --upgrade pip

if [ -f "$repo_root/requirements.txt" ]; then
  "$venv_dir/bin/python" -m pip install -r "$repo_root/requirements.txt"
fi

cat <<EOF
Agent virtual environment ready.

Repo: $repo_root
Venv: $venv_dir
Python: $("$venv_dir/bin/python" --version)

Activate with:
  source "$venv_dir/bin/activate"
EOF
