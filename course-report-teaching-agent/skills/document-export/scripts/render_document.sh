#!/usr/bin/env bash
set -u

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
skill_dir="$(dirname -- "$script_dir")"

if [ -x "$skill_dir/.venv/bin/python" ]; then
  exec "$skill_dir/.venv/bin/python" "$script_dir/render_document.py" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$script_dir/render_document.py" "$@"
fi

printf '%s\n' '{"status":"error","error":"python3 runtime not found; install dependencies from requirements.txt in the skill .venv"}' >&2
exit 2
