@echo off
chcp 65001 >nul
cd /d D:\python_projects\ocr_read\venv_clean

echo 清理 __pycache__...
for /r Lib\site-packages /d %%D in (__pycache__) do rmdir /s /q "%%D" 2>nul

echo 清理 *.pyc...
for /r Lib\site-packages /s %%F in (*.pyc) do del "%%F" 2>nul

echo 清理测试文件...
rmdir /s /q Lib\site-packages\tests 2>nul

echo 清理文档...
rmdir /s /q Lib\site-packages\*-*.dist-info 2>nul

echo 完成！
pause