@echo off
rem Запуск Optimizer Game с правами администратора (запрос UAC).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Виртуальное окружение не найдено. Сначала запустите setup.bat
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~dp0.venv\Scripts\pythonw.exe' -ArgumentList 'main.py' -WorkingDirectory '%~dp0' -Verb RunAs"
