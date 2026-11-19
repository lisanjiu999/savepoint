@echo off
setlocal
pushd "%~dp0"

rem Optional: switch to a mirror if PyPI is slow or blocked.
set "MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"

rem Keep pip cache and temp files inside the project directory.
set "PIP_CACHE_DIR=%~dp0.cache\pip"
set "TMP=%~dp0.tmp"
set "TEMP=%~dp0.tmp"
if not exist "%TMP%" mkdir "%TMP%"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found in PATH. Install Python 3.10+ first.
  popd
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating virtualenv .venv ...
  python -m venv --system-site-packages .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtualenv.
    popd
    pause
    exit /b 1
  )
)

echo [2/2] Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt" -i "%MIRROR%"
if errorlevel 1 (
  echo.
  echo [ERROR] Install failed. Try without the mirror:
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  popd
  pause
  exit /b 1
)

echo.
echo Done. Launch with run.bat
popd
pause