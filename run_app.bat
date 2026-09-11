@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto setup
if not exist ".venv\.learn_setup_v2" goto setup

".venv\Scripts\python.exe" -m pip check >nul 2>&1
if errorlevel 1 goto setup
goto launch

:setup
call "%~dp0setup_app.bat"
if errorlevel 1 (
  echo.
  echo Setup did not complete. Review the message above.
  pause
  exit /b 1
)

:launch
echo.
echo Starting Learn Library Builder...
echo Your browser will open automatically. Keep this window open while using the app.
echo Press Ctrl+C in this window when you are finished.
".venv\Scripts\python.exe" -m shiny run --host 127.0.0.1 --port 0 --launch-browser --no-dev-mode app.py

if errorlevel 1 (
  echo.
  echo The app stopped because of an error.
  pause
  exit /b 1
)
