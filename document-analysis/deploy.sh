#!/bin/bash
set -e

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip

if command -v uv >/dev/null 2>&1; then
    uv pip install -r requirements.txt
else
    pip install -r requirements.txt
fi

python3 main.py
