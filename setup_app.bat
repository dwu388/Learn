@echo off
setlocal
cd /d "%~dp0"

set "BASE_PYTHON="
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import struct,sys; raise SystemExit(0 if sys.version_info >= (3,11) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
  if not errorlevel 1 set "BASE_PYTHON=py -3"
)

if not defined BASE_PYTHON (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "import struct,sys; raise SystemExit(0 if sys.version_info >= (3,11) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_PYTHON=python"
  )
)

if not defined BASE_PYTHON (
  echo Python was not found, is older than 3.11, or is not 64-bit.
  echo Install 64-bit Python 3.11 or newer from https://www.python.org/downloads/windows/
  echo During installation, enable the Python launcher or Add Python to PATH.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the private Python environment...
  %BASE_PYTHON% -m venv .venv
  if errorlevel 1 exit /b 1
)

echo Updating installation tools...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1

echo Installing Learn Library Builder dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade -r requirements.txt
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m pip check
if errorlevel 1 exit /b 1

> ".venv\.learn_setup_v2" echo ready

".venv\Scripts\python.exe" -c "from learn_processor.youtube import detect_javascript_runtime; raise SystemExit(0 if detect_javascript_runtime() else 1)" >nul 2>&1
if not errorlevel 1 goto runtime_ready

echo.
echo NOTE: EPUB, PDF, and YouTube caption processing are ready.
echo For reliable YouTube audio download and Whisper fallback, install Deno 2 or newer:
echo   winget install DenoLand.Deno
echo Then close and reopen this app.
goto setup_complete

:runtime_ready
echo YouTube JavaScript runtime detected.

:setup_complete
echo Setup completed successfully.
exit /b 0
