@echo off
setlocal
cd /d "%~dp0"

if not exist "tool\.venv\Scripts\python.exe" (
  echo The toolkit is not installed yet. Run setup_windows.bat first.
  pause
  exit /b 1
)

set "PYTHONDONTWRITEBYTECODE=1"
"tool\.venv\Scripts\python.exe" "tool\student_export.py"
set "RESULT=%ERRORLEVEL%"
echo.
if "%RESULT%"=="0" (
  echo EXPORT FINISHED. Open output_packages and check the newest folder.
) else (
  echo EXPORT FAILED. Keep all files and ask your AI assistant to read the error.
)
pause
exit /b %RESULT%

