@echo off
title LaunchPad - local app hosting
cd /d "%~dp0"

set "PY=python"
%PY% --version >nul 2>nul || set "PY=py"
%PY% --version >nul 2>nul || (
  echo.
  echo   Python was not found on this computer.
  echo   Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  echo.
  pause
  exit /b
)

rem Optional extra: phone QR codes. LaunchPad works fine without it.
%PY% -c "import qrcode" >nul 2>nul || (
  echo   One-time setup: adding phone QR codes...
  %PY% -m pip install --quiet qrcode pillow >nul 2>nul
)

%PY% launchpad.py %*
pause
