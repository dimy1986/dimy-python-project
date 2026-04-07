# 打包成 EXE 指南

## 前置条件

| 要求 | 说明 |
|------|------|
| Python 3.10 / 3.11（64-bit） | 推荐 3.10，与 PaddlePaddle 兼容性最佳 |
| 已激活的虚拟环境 | 见下方步骤 |
| OCR 模型文件 | 打包完成后手动放置（见步骤 4） |

---

## 步骤 1：安装依赖

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> **注意**：`paddlepaddle` 体积较大（~300 MB），首次安装耗时较长。

---

## 步骤 2：打包

双击 `build_advanced.bat`，或在已激活虚拟环境的命令行中运行：

```bat
pyinstaller --noconfirm --clean ocr_tool.spec
```

打包完成后，可执行程序位于：

```
dist\ocr_tool\ocr_tool.exe
```

---

## 步骤 3：放置 OCR 模型

程序**不会**把模型文件打进 EXE，需要在 `dist\ocr_tool\` 旁边建立如下目录结构：

```
dist\
└── ocr_tool\
    ├── ocr_tool.exe
    └── ocr_models\
        ├── ch_PP-OCRv4_det_infer\
        ├── ch_PP-OCRv4_rec_infer\
        └── ch_ppocr_mobile_v2.0_cls_infer\
```

模型下载地址（PaddleOCR 官方）：  
<https://paddlepaddle.github.io/PaddleOCR/latest/model/PP-OCRv4/PP-OCRv4_server_det.html>

---

## 步骤 4：分发

将整个 `dist\ocr_tool\` 文件夹（含 `ocr_models\`）复制到目标 Windows 机器，双击 `ocr_tool.exe` 即可运行，**无需安装 Python**。

---

## 常见问题

| 现象 | 解决方法 |
|------|----------|
| 启动闪退 | 查看同目录下的 `ocr_app.log` 日志文件 |
| 找不到模型 | 确认 `ocr_models\` 和 `ocr_tool.exe` 在同一目录 |
| `DLL load failed` | 安装 [Visual C++ 2019 Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| 打包时 `ModuleNotFoundError` | 在 `ocr_tool.spec` 的 `extra_hiddenimports` 中添加缺失模块名 |
