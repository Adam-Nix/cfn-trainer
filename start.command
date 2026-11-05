#!/bin/bash
# Double-click on macOS (or run on Linux). First run installs requirements into a local .venv.
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then echo "Python 3 not found - install it from https://www.python.org/downloads/"; read -r -p "Press Enter"; exit 1; fi
[ -x .venv/bin/python ] || "$PY" -m venv .venv || { echo "Could not create .venv"; read -r -p "Press Enter"; exit 1; }
source .venv/bin/activate
python -c "import cfnlint, moto, yaml, boto3" 2>/dev/null || { echo "Installing requirements (first run only)..."; python -m pip install -q -r requirements.txt || { echo "Install failed - check your internet connection."; read -r -p "Press Enter"; exit 1; }; }
python app.py
