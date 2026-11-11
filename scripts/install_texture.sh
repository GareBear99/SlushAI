#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate || { echo "Run scripts/setup_venv.sh first"; exit 1; }
# Clone TEXTure (text-guided mesh texturing)
if [ ! -d vendors/TEXTurePaper ]; then
  git clone https://github.com/TEXTurePaper/TEXTurePaper.git vendors/TEXTurePaper
fi
cd vendors/TEXTurePaper
pip install -r requirements.txt || true
# TEXTure typically needs torch + diffusers
pip install diffusers transformers accelerate safetensors einops
python - <<'PY'
try:
  import torch; print('torch ok')
except Exception:
  import sys, subprocess
  subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'torch', '--index-url', 'https://download.pytorch.org/whl/cpu'])
PY

echo "✅ TEXTure vendor ready. Usage is driven by pipeline wrapper."
