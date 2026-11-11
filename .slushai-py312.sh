#!/usr/bin/env bash
# Install a user-local Python 3.12 (no admin) via uv.
# WHY: torch ships NO macOS x86_64 (Intel) wheels since 2.3.0 — 2.5.1's macOS
# wheels are arm64-only and its cp313 wheel is manylinux-only. The last torch
# with an Intel-mac wheel is 2.2.2, which needs Python <=3.12. This Mac only
# has Python 3.13, so a 3.12 interpreter is required to run TripoSR at all.
# uv installs standalone CPython builds under ~/.local/share/uv/python.
cd "$(dirname "$0")"
set -u
exec > >(tee -a logs/py312-install.log) 2>&1
say() { echo "[py312 $(date +%H:%M:%S)] $*"; }
say "=== Python 3.12 install (uv, user-local) ==="
if [ ! -x "$HOME/.local/bin/uv" ]; then
  say "installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || { say "FATAL: uv install failed"; exit 1; }
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.12 || { say "FATAL: uv python install 3.12 failed"; exit 1; }
UV_PY=$(uv python find 3.12)
say "python 3.12 at: $UV_PY"
"$UV_PY" --version
say "=== Python 3.12 ready ==="
