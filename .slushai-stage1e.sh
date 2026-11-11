#!/usr/bin/env bash
# SlushAI Stage 1e — TripoSR deps install + generation test.
# The one-shot `pip install -r requirements-triposr.txt` cannot work:
# torchmcubes must build against an ALREADY-INSTALLED torch, but pip builds
# it in isolation before torch is installed. So: install torch + the rest
# first, then torchmcubes with --no-build-isolation, then run the gen test.
# Run AFTER stage1d finishes (two pip runs on one venv must not overlap).
# Logs to logs/stage1-triposr-install.log / logs/stage1-gen-results.txt.
set -u
set -o pipefail
cd "$(dirname "$0")"
# The venv's bin dir on PATH: the venv's cmake/ninja are there, and any
# source build in this install (llvmlite, torchmcubes) needs `cmake`.
export PATH="$PWD/.venv/bin:$PATH"
exec > >(tee -a logs/stage1-triposr.log) 2>&1
say() { echo "[stage1e $(date +%H:%M:%S)] $*"; }
say "=== TripoSR deps install ==="
say "--- step 1: torch + the rest (no torchmcubes yet) ---"
.venv/bin/python -m pip install torch==2.2.2 omegaconf==2.3.0 einops==0.7.0 transformers==4.35.0 rembg numba==0.62.1 llvmlite==0.45.0 huggingface-hub "imageio[ffmpeg]" "gradio>=4.0,<6" moderngl==5.10.0 > logs/stage1-triposr-install.log 2>&1 || { say "FATAL: torch+deps install failed (see logs/stage1-triposr-install.log)"; exit 1; }
say "torch + deps installed"
say "--- step 2: torchmcubes against the installed torch ---"
.venv/bin/python -m pip install scikit-build-core >> logs/stage1-triposr-install.log 2>&1 || { say "FATAL: scikit-build-core install failed"; exit 1; }
.venv/bin/python -m pip install --no-build-isolation git+https://github.com/tatsy/torchmcubes.git >> logs/stage1-triposr-install.log 2>&1 || { say "FATAL: torchmcubes build failed (see logs/stage1-triposr-install.log)"; exit 1; }
say "torchmcubes installed"
say "--- generation test ---"
bash .slushai-stage1b.sh
say "=== Stage 1e done ==="
