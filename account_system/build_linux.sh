#!/bin/bash
# 账户与交易查询系统 - Linux / macOS 打包脚本
# 打包完成后将 dist/query_system/ 整个目录拷贝到目标机器运行

set -e
echo "============================================================"
echo "  账户与交易查询系统 - Linux/macOS 打包脚本"
echo "  打包完成后将 dist/query_system/ 拷贝到目标机器"
echo "============================================================"
echo

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.8+"
    exit 1
fi

# 创建或复用虚拟环境
echo "[1/4] 准备虚拟环境..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "      虚拟环境已创建：.venv/"
else
    echo "      复用已有虚拟环境：.venv/"
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/4] 安装依赖..."
pip install -r requirements.txt --upgrade -q
pip install pyinstaller --upgrade -q

echo "[3/4] 清理旧构建..."
rm -rf dist/query_system build/query_system

echo "[4/4] 打包中，请耐心等待（约 1-3 分钟）..."
pyinstaller query_system.spec --noconfirm

echo
echo "============================================================"
echo "  打包成功！"
echo "  输出目录：dist/query_system/"
echo "  在目标机器上运行：./dist/query_system/query_system"
echo "============================================================"
