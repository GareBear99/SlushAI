#!/usr/bin/env bash
# Deep torch diagnosis: write everything to logs/diag-torch.txt
cd "$(dirname "$0")"
{
echo "=== python / pip ==="
.venv/bin/python --version
.venv/bin/python -m pip --version
echo "=== platform tags pip accepts ==="
.venv/bin/python -m pip debug --verbose 2>/dev/null | grep -A 12 "Compatible tags"
echo "=== torch versions pip sees ==="
.venv/bin/python -m pip index versions torch 2>&1 | head -5
echo "=== torch 2.5.1 metadata from PyPI JSON API ==="
curl -s https://pypi.org/pypi/torch/2.5.1/json | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('requires_python:', d['info'].get('requires_python')); print('files:', len(d['urls'])); [print(' ', u['filename']) for u in d['urls'] if 'macosx' in u['filename'] and 'x86_64' in u['filename']]"
echo "=== torch 2.6.0 files (next release) for comparison ==="
curl -s https://pypi.org/pypi/torch/2.6.0/json | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('requires_python:', d['info'].get('requires_python')); [print(' ', u['filename']) for u in d['urls'] if 'macosx' in u['filename'] and 'x86_64' in u['filename']][:6]"
} > logs/diag-torch.txt 2>&1
echo "diagnostic written to logs/diag-torch.txt"
