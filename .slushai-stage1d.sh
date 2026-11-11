#!/usr/bin/env bash
# SlushAI Stage 1d — xatlas fix (run once, in the project root).
# The stock xatlas 0.0.9 sdist cannot build on this Mac: its bundled pybind11
# declares cmake_minimum_required(VERSION 3.4), and the installed CMake has
# removed compatibility with CMake < 3.5. This downloads the sdist, bumps
# that minimum to 3.5, builds a wheel, and installs it — plus the rest of the
# pipeline deps (the earlier pip run died on xatlas before installing
# anything). Logs to logs/stage1d-xatlas.log.
set -u
set -o pipefail
cd "$(dirname "$0")"
VENV_PY="$PWD/.venv/bin/python"
# The venv's bin dir must be on PATH: the wheel build spawns `cmake`/`ninja`
# as plain commands, and the script does not activate the venv.
export PATH="$PWD/.venv/bin:$PATH"
exec > >(tee -a logs/stage1d-xatlas.log) 2>&1
say() { echo "[stage1d $(date +%H:%M:%S)] $*"; }
say "=== xatlas fix ==="
say "--- pipeline deps except xatlas ---"
# numpy is PINNED to 1.26.4 (last 1.x with cp312 wheels): PyMCubes 0.1.4
# builds its C extension against oldest-supported-numpy (1.26.4 for cp312),
# so with numpy 2.x at runtime the import fails with "numpy.dtype size
# changed, may indicate binary incompatibility" (verified 2026-11-10).
# On Python 3.13 the same combo worked only because no numpy 1.x exists
# for cp313, so the build used numpy 2 headers. Do NOT bump to numpy 2
# while PyMCubes 0.1.4 is in the stack.
"$VENV_PY" -m pip install "numpy==1.26.4" Pillow==11.3.0 trimesh==4.0.5 PyMCubes==0.1.4 || { say "FATAL: pipeline deps install failed"; exit 1; }
say "pipeline deps (minus xatlas) installed"
say "--- xatlas: download sdist, patch, build wheel ---"
rm -rf /tmp/xatlas-build
mkdir -p /tmp/xatlas-build
# --no-build-isolation: without it, `pip download` hangs for minutes preparing
# metadata in an isolated env (observed 2026-11-10: stuck >6 min, killed).
"$VENV_PY" -m pip download --no-build-isolation xatlas==0.0.9 --no-deps --no-binary :all: -d /tmp/xatlas-build || { say "FATAL: xatlas sdist download failed"; exit 1; }
cd /tmp/xatlas-build
tar xzf xatlas-0.0.9.tar.gz
cd xatlas-0.0.9
say "cmake_minimum_required lines (before patch):"
grep -rn "cmake_minimum_required" CMakeLists.txt extern/pybind11/CMakeLists.txt || true
# Bump every cmake_minimum_required below 3.5 up to 3.5 (BSD sed, -E).
grep -rlE "cmake_minimum_required\(VERSION (2|3\.[0-4])" . | while read -r f; do
  say "patching $f"
  sed -E -i '' 's/cmake_minimum_required\(VERSION (2[^)]*|3\.[0-4][^)]*)\)/cmake_minimum_required(VERSION 3.5)/' "$f"
done
say "cmake_minimum_required lines (after patch):"
grep -rn "cmake_minimum_required" CMakeLists.txt extern/pybind11/CMakeLists.txt || true
say "--- build wheel ---"
# --no-build-isolation again (same hang otherwise); pybind11 must be in the
# venv first since there is no isolated build env to provide it.
# cmake + ninja: the stock build gets them from pip's isolated build env;
# with --no-build-isolation they must be in the venv (no system cmake here).
"$VENV_PY" -m pip install pybind11 cmake ninja || { say "FATAL: pybind11/cmake/ninja install failed"; exit 1; }
"$VENV_PY" -m pip wheel --no-build-isolation . -w /tmp/xatlas-build/wheels --no-deps || { say "FATAL: xatlas wheel build failed"; exit 1; }
say "--- install wheel ---"
"$VENV_PY" -m pip install /tmp/xatlas-build/wheels/xatlas-*.whl || { say "FATAL: xatlas wheel install failed"; exit 1; }
cd /Users/gary/projects/AI3DModeller
say "--- verify pipeline imports ---"
"$VENV_PY" -c "import numpy, PIL, trimesh, mcubes, xatlas; print('numpy', numpy.__version__, '| Pillow', PIL.__version__, '| xatlas OK, PyMCubes OK, trimesh OK')" || { say "FATAL: pipeline import check failed"; exit 1; }
say "=== xatlas fix done ==="
