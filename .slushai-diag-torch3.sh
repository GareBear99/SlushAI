#!/usr/bin/env bash
# List ALL torch release files + check for a Python 3.12 interpreter.
cd "$(dirname "$0")"
{
echo "=== torch 2.5.1 ALL files ==="
curl -s https://pypi.org/pypi/torch/2.5.1/json | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); [print(' ', u['filename']) for u in d['urls']]"
echo "=== torch 2.4.1 macosx files ==="
curl -s https://pypi.org/pypi/torch/2.4.1/json | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('requires_python:', d['info'].get('requires_python')); [print(' ', u['filename']) for u in d['urls'] if 'macosx' in u['filename']]"
echo "=== can pip fetch a cp312 Intel-mac wheel for 2.5.1? ==="
.venv/bin/python -m pip download --no-deps --only-binary=:all: --platform macosx_10_9_x86_64 --python-version 312 --abi cp312 -d /tmp/torch312 torch==2.5.1 2>&1 | tail -3
ls -la /tmp/torch312/ 2>/dev/null
echo "=== python interpreters on this Mac ==="
ls /usr/local/bin/python* /Library/Frameworks/Python.framework/Versions/*/bin/python3* 2>/dev/null
which -a python3.12 python3.11 python3 2>/dev/null
which brew 2>/dev/null; brew --version 2>/dev/null | head -1
} > logs/diag-torch3.txt 2>&1
echo "diagnostic written to logs/diag-torch3.txt"
