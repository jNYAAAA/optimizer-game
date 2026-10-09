@echo off
rem Запуск Optimizer Game без окна консоли.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main.py
) else (
    echo Виртуальное окружение не найдено. Сначала запустите setup.bat
    pause
    exit /b 1
)
