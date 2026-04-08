@echo off
chcp 65001 > nul

REM 获取当前脚本所在目录（这是 dimy-python-project 目录）
cd /d "%~dp0"

REM 虚拟环境在上一级目录
set VENV_DIR=%cd%\..\venv_clean
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe

REM 验证虚拟环境存在
if not exist "%PYTHON_EXE%" (
    echo 错误: 找不到虚拟环境！
    echo.
    echo 期望的目录结构:
    echo ocr_read/
    echo ├── venv_clean/
    echo ├── dimy-python-project/
    echo │   └── run.bat
    echo └── ocr_models/
    echo.
    pause
    exit /b 1
)

REM 用虚拟环境的 python 运行程序
"%PYTHON_EXE%" main.py

pause