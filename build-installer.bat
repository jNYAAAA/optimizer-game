@echo off
rem Сборка OptimizerGame.exe и установщика (Inno Setup).
setlocal
cd /d "%~dp0"

set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo Inno Setup не найден. Установите его: winget install JRSoftware.InnoSetup
    pause
    exit /b 1
)

echo [1/4] Генерация ресурсов...
".venv\Scripts\python.exe" assets\make_icon.py
".venv\Scripts\python.exe" assets\make_check.py
".venv\Scripts\python.exe" assets\make_installer_art.py
if errorlevel 1 goto :error

echo [2/4] Сборка .exe (может занять несколько минут)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean OptimizerGame.spec
if errorlevel 1 goto :error

echo [3/4] Сборка установщика...
%ISCC% installer.iss
if errorlevel 1 goto :error

echo [4/4] Готово: dist_installer\OptimizerGame-Setup.exe
pause
exit /b 0

:error
echo.
echo Ошибка сборки. Проверьте вывод выше.
pause
exit /b 1
