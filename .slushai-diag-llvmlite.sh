#!/usr/bin/env bash
# Which numba/llvmlite versions still ship cp312 macOS x86_64 wheels?
cd "$(dirname "$0")"
{
echo "=== llvmlite: cp312 macosx_x86_64 files per version ==="
for v in 0.46.0 0.45.0 0.44.0 0.43.0; do
  echo "-- llvmlite $v --"
  curl -s "https://pypi.org/pypi/llvmlite/$v/json" | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('requires_python:', d['info'].get('requires_python')); [print(' ', u['filename']) for u in d['urls'] if 'macosx' in u['filename'] and 'x86_64' in u['filename'] and 'cp312' in u['filename']]"
done
echo "=== numba: llvmlite requirement + cp312 macosx_x86_64 files ==="
for v in 0.63.1 0.62.1 0.62.0 0.61.2 0.61.0; do
  echo "-- numba $v --"
  curl -s "https://pypi.org/pypi/numba/$v/json" | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('requires_python:', d['info'].get('requires_python')); print('requires:', [r for r in d['info'].get('requires_dist') or [] if 'llvmlite' in r.lower() or 'numpy' in r.lower()]); [print(' ', u['filename']) for u in d['urls'] if 'macosx' in u['filename'] and 'x86_64' in u['filename'] and 'cp312' in u['filename']]"
done
echo "=== pymatting: numba requirement ==="
curl -s https://pypi.org/pypi/pymatting/json | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('latest:', d['info']['version']); print('requires:', d['info'].get('requires_dist'))"
} > logs/diag-llvmlite.txt 2>&1
echo "diagnostic written to logs/diag-llvmlite.txt"
