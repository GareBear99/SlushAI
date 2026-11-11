#!/usr/bin/env bash
# Diagnose why pip cannot find torch==2.5.1 ("from versions: none").
cd "$(dirname "$0")"
.venv/bin/python -m pip --version
.venv/bin/python -m pip config list
echo "--- pypi torch index ---"
curl -s -o /dev/null -w 'pypi torch index: %{http_code}
' https://pypi.org/simple/torch/
echo "--- pip index versions torch ---"
.venv/bin/python -m pip index versions torch 2>&1 | head -8
echo "--- dry-run torch 2.5.1 ---"
.venv/bin/python -m pip install --dry-run --no-deps torch==2.5.1 2>&1 | tail -6
