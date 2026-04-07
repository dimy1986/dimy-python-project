@echo off
setlocal DisableDelayedExpansion
chcp 65001 > nul

cd /d "%~dp0"

echo ============================================================
echo  OCR Tool -- PyInstaller packaging script
echo ============================================================

REM -- 1. Kill any running instance so PyInstaller can overwrite files ----------
taskkill /F /IM ocr_tool.exe >nul 2>nul

REM -- 2. Activate virtual environment (adjust path if needed) ------------------
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
) else if exist "%~dp0..\venv\Scripts\activate.bat" (
    call "%~dp0..\venv\Scripts\activate.bat"
) else if exist "D:\python_projects\ocr_read\venv_clean\Scripts\activate.bat" (
    call "D:\python_projects\ocr_read\venv_clean\Scripts\activate.bat"
) else (
    echo [WARN] No venv found -- using system Python.
)

REM -- 3. Verify key packages ---------------------------------------------------
python -c "import paddleocr; import paddle; import fitz; import cv2; import pandas; import openpyxl; print('[OK] all required modules found')"
if errorlevel 1 (
    echo [ERROR] One or more required packages are missing.
    echo         Run:  pip install -r requirements.txt
    pause
    exit /b 1
)

REM -- 4. Run PyInstaller -------------------------------------------------------
set "DISTPATH=%~dp0dist"
set "WORKPATH=%~dp0build"

echo.
echo [INFO] Output folder : %DISTPATH%\ocr_tool\
echo [INFO] Build folder  : %WORKPATH%
echo.

pyinstaller --noconfirm --clean ^
    --distpath "%DISTPATH%" ^
    --workpath "%WORKPATH%" ^
    "%~dp0ocr_tool.spec"

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller packaging failed.
    pause
    exit /b 1
)

REM -- 5. Remind user to copy OCR models ----------------------------------------
echo.
echo ============================================================
echo  Build complete!  Executable is at:
echo    %DISTPATH%\ocr_tool\ocr_tool.exe
echo.
echo  IMPORTANT: copy the ocr_models\ folder next to the exe:
echo    %DISTPATH%\ocr_tool\ocr_models\ch_PP-OCRv4_det_infer\
echo    %DISTPATH%\ocr_tool\ocr_models\ch_PP-OCRv4_rec_infer\
echo    %DISTPATH%\ocr_tool\ocr_models\ch_ppocr_mobile_v2.0_cls_infer\
echo ============================================================
pause
