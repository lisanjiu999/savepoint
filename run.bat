@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo [ERROR] Virtualenv .venv not found. Run setup.bat first.
  popd
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m savepoint
popd