#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate || { echo "Run scripts/setup_venv.sh first"; exit 1; }
# Clone TripoSR backend
if [ ! -d vendors/TripoSR ]; then
  git clone https://github.com/VAST-AI-Research/TripoSR.git vendors/TripoSR
fi
cd vendors/TripoSR
pip install -r requirements.txt || true
# Ensure torch (CPU) is present (skip if already installed)
python - <<'PY'
try:
  import torch; print('torch ok')
except Exception:
  import sys, subprocess
  subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'torch', '--index-url', 'https://download.pytorch.org/whl/cpu'])
PY

echo "✅ TripoSR vendor ready. Usage is driven by pipeline wrapper."
