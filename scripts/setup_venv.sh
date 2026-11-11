#!/usr/bin/env bash
# SlushAI 3D Modeller — build the virtual environment and install dependencies.
# Run from the project root:  bash scripts/setup_venv.sh
# (or: ./scripts/setup_venv.sh after chmod +x)
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
$PY -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
# Full dependency set (Flask backend + pipeline + TripoSR, CPU-only on this Mac).
pip install -r requirements.txt
echo "venv ready. Activate with: source .venv/bin/activate"
echo "Start the server with:  SLUSHAI_PORT=5000 .venv/bin/python viewer/app.py"
