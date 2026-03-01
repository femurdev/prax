#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python main.py
fi
if [[ -x .venv/bin/python3 ]]; then
  exec .venv/bin/python3 main.py
fi
exec python3 main.py
