@echo off
chcp 65001 > nul
set PYTHON=%~dp0python.exe
set SCRIPT=%~dp0your_script.py
set DIST=%~dp0dist\

if not exist "%DIST%" mkdir "%DIST%"

pyinstaller --onefile --distpath "%DIST%" "%SCRIPT%"