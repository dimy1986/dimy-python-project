@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM Quick one-command build using the spec file.
REM For full control use build_advanced.bat instead.

pyinstaller --noconfirm --clean ocr_tool.spec

if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo Done. See dist\ocr_tool\ocr_tool.exe
pause
