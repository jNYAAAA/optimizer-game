@echo off
rem Сборка OptimizerGame.exe (один файл).
setlocal
cd /d "%~dp0"

echo [1/4] Установка инструментов сборки...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller pillow
if errorlevel 1 goto :error

echo [2/4] Генерация иконки...
".venv\Scripts\python.exe" assets\make_icon.py
if errorlevel 1 goto :error

echo [3/4] Сборка .exe (может занять несколько минут)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean OptimizerGame.spec
if errorlevel 1 goto :error

echo [4/4] Готово: dist\OptimizerGame.exe
pause
exit /b 0

:error
echo.
echo Ошибка сборки. Проверьте вывод выше.
pause
exit /b 1
