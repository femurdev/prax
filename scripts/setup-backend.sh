#!/usr/bin/env bash
# Recreate backend venv with current system Python (fixes "No such file or directory" if Python was upgraded)
set -e
cd "$(dirname "$0")/../backend"
echo "Using: $(python3 --version)"
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
echo "Done. Run: npm start"
