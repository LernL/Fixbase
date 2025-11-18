@echo off
REM Ця команда гарантує, що скрипт виконується саме з папки demoinstaller
cd /d "%~dp0"

echo Building fixbase.exe...

REM Запуск PyInstaller.
REM "..\code\fixbase.py" вказує шукати файл у сусідній папці.
REM --distpath . змушує покласти готовий .exe прямо сюди (у demoinstaller), а не створювати папку dist.

pyinstaller --noconsole --onefile --distpath . "..\code\fixbase.py"

echo.
echo Build complete!

REM (Опціонально) Очищення сміття після збірки
echo Cleaning up temporary files...
if exist build rmdir /s /q build
if exist __pycache__ rmdir /s /q __pycache__
if exist fixbase.spec del fixbase.spec

pause