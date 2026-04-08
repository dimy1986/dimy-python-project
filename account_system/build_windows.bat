@echo off
chcp 65001 >nul
echo ============================================================
echo   账户与交易查询系统 - Windows 打包脚本
echo   打包完成后，将 dist\query_system\ 整个文件夹拷贝给目标电脑
echo ============================================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+ 并添加到 PATH
    pause
    exit /b 1
)

:: 安装/升级依赖
echo [1/3] 安装依赖...
pip install -r requirements.txt --upgrade -q
if errorlevel 1 (
    echo [错误] 运行时依赖安装失败，请检查网络或 pip 配置
    pause
    exit /b 1
)
pip install pyinstaller --upgrade -q
if errorlevel 1 (
    echo [错误] pyinstaller 安装失败，请检查网络或 pip 配置
    pause
    exit /b 1
)

:: 清理旧的构建产物
echo [2/3] 清理旧构建...
if exist dist\query_system rmdir /s /q dist\query_system
if exist build\query_system rmdir /s /q build\query_system

:: 执行打包
echo [3/3] 打包中，请耐心等待（约 1-3 分钟）...
pyinstaller query_system.spec --noconfirm
if errorlevel 1 (
    echo [错误] 打包失败，请查看上方错误信息
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   打包成功！
echo   输出目录：dist\query_system\
echo   请将整个 dist\query_system\ 文件夹拷贝到目标电脑
echo   目标电脑上双击 query_system.exe 即可启动
echo ============================================================
pause
