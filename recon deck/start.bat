@echo off
setlocal
cd /d "%~dp0"
set "ELECTRON=node_modules\electron\dist\electron.exe"
if not exist "%ELECTRON%" (
  echo.
  echo   Electron runtime not found.
  echo   Install Node.js, then run "npm install" in this folder.
  echo.
  pause
  exit /b 1
)
start "" "%ELECTRON%" "%~dp0."
exit /b 0
