@echo off
cd /d "%~dp0"

echo Building fixbase.exe...

pyinstaller --noconsole --onefile --distpath "%~dp0.." "..\code\fixbase.py"

echo.
echo Build complete!

echo Cleaning up temporary files...
if exist build rmdir /s /q build
if exist __pycache__ rmdir /s /q __pycache__
if exist fixbase.spec del fixbase.spec

pause
