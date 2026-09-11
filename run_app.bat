@echo off
setlocal
cd /d "%~dp0"

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" || (
  echo Python 3.11 or newer is required.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment...
  py -3 -m venv .venv || exit /b 1
)

echo Checking dependencies...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt || (
  echo Dependency installation failed.
  pause
  exit /b 1
)

echo Opening Learn Library Builder at http://127.0.0.1:8000
.venv\Scripts\python.exe -m shiny run --host 127.0.0.1 --port 8000 --launch-browser app.py

if errorlevel 1 pause
