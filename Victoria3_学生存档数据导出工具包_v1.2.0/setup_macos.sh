#!/bin/bash
set -u
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.11 or newer from python.org."
  exit 1
fi

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'
if [ $? -ne 0 ]; then
  echo "Python is older than 3.11. Install a newer version."
  exit 1
fi

python3 -m venv "tool/.venv" || exit 1
"tool/.venv/bin/python" -m pip install --upgrade pip || exit 1
"tool/.venv/bin/python" -m pip install -r "tool/requirements_student.txt" || exit 1

echo
echo "SETUP COMPLETE"

