@echo off
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3.9 or newer was not found.
  echo Install it from https://www.python.org/downloads/ then double-click this file again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv || (echo Could not create the virtual environment. & pause & exit /b 1)
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -c "import cfnlint, moto, yaml, boto3" >nul 2>nul
if errorlevel 1 (
  echo Installing requirements - first run only, about a minute...
  "%VPY%" -m pip install -q -r requirements.txt || (echo Install failed - check your internet connection. & pause & exit /b 1)
)
"%VPY%" app.py
pause
