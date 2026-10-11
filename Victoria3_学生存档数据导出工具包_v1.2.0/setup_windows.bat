@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
py -3.13 --version >nul 2>&1 && set "PYTHON_CMD=py -3.13"
if not defined PYTHON_CMD py -3.12 --version >nul 2>&1 && set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD py -3.11 --version >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD python --version >nul 2>&1 && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo Python 3.11 or newer was not found.
  echo Install 64-bit Python from python.org, then run this file again.
  pause
  exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo Python is older than 3.11. Install a newer 64-bit version.
  pause
  exit /b 1
)

%PYTHON_CMD% -m venv "tool\.venv"
if errorlevel 1 goto :failed

"tool\.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"tool\.venv\Scripts\python.exe" -m pip install -r "tool\requirements_student.txt"
if errorlevel 1 goto :failed

echo.
echo SETUP COMPLETE
pause
exit /b 0

:failed
echo.
echo SETUP FAILED. Keep this window and ask your AI assistant to read the error.
pause
exit /b 1

