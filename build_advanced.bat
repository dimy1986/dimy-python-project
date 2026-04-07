@echo off
setlocal DisableDelayedExpansion
chcp 65001 > nul

cd /d "%~dp0"

REM Kill running exe so PyInstaller can overwrite files
taskkill /F /IM ocr_tool.exe >nul 2>nul

call "%~dp0..\venv_clean\Scripts\activate.bat"

python -c "import paddleocr; import paddle; import pyclipper; import pdf2image; import cv2; print('all modules ok')"

if errorlevel 1 (
    echo check failed
    pause
    exit /b 1
)

REM Use absolute paths under this script folder
set "DISTPATH=%~dp0dist"
set "WORKPATH=%~dp0build"

echo packing...
echo DISTPATH=%DISTPATH%
echo Output exe folder: %DISTPATH%ocr_tool\

pyinstaller --noconfirm --clean --distpath "%DISTPATH%" --workpath "%WORKPATH%" "%~dp0ocr_tool.spec"

if errorlevel 1 (
    echo package failed
    pause
    exit /b 1
)

echo package complete
