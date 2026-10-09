@echo off
rem Первичная установка: создаёт .venv и ставит зависимости.
setlocal
cd /d "%~dp0"

echo [1/3] Создание виртуального окружения...
python -m venv .venv
if errorlevel 1 (
    echo Не найден Python. Установите его с https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [2/3] Обновление pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo [3/3] Установка зависимостей...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Готово! Запускайте приложение через run.bat (или run-as-admin.bat).
pause
