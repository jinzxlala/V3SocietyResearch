#!/bin/bash
set -u
cd "$(dirname "$0")"

if [ ! -x "tool/.venv/bin/python" ]; then
  echo "The toolkit is not installed yet. Run: bash setup_macos.sh"
  exit 1
fi

export PYTHONDONTWRITEBYTECODE=1
"tool/.venv/bin/python" "tool/student_export.py"
RESULT=$?
echo
if [ $RESULT -eq 0 ]; then
  echo "EXPORT FINISHED. Open output_packages and check the newest folder."
else
  echo "EXPORT FAILED. Keep all files and ask your AI assistant to read the error."
fi
exit $RESULT

