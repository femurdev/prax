#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend"
# Prefer venv; try python3.12 first (in case python/python3 point at missing 3.11)
for py in .venv/bin/python3.12 .venv/bin/python3 .venv/bin/python; do
  if [[ -x "$py" ]] && "$py" -c "import sys; sys.exit(0)" 2>/dev/null; then
    exec "$py" main.py
  fi
done
exec python3 main.py
