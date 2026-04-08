# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for the Account & Transaction Query System
# Build command (run from the account_system/ directory):
#   pyinstaller query_system.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[str(Path("app.py").parent.resolve())],
    binaries=[],
    # Bundle the templates directory into the package
    datas=[
        ("templates", "templates"),
    ],
    hiddenimports=[
        # Flask internals sometimes missed by the auto-analyzer
        "flask",
        "flask.templating",
        "jinja2",
        "jinja2.ext",
        "werkzeug",
        "werkzeug.serving",
        "werkzeug.routing",
        "werkzeug.exceptions",
        # pandas / openpyxl
        "pandas",
        "openpyxl",
        "openpyxl.cell._writer",
        # SQLite (usually built-in, listed for safety)
        "sqlite3",
        "_sqlite3",
        # database module
        "database",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages not needed at runtime
        "matplotlib",
        "PIL",
        "cv2",
        "paddleocr",
        "paddle",
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="query_system",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,       # 保留控制台窗口，方便查看运行日志；如不需要可改为 False
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",  # 如有图标文件，取消注释并修改路径
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="query_system",  # 输出文件夹名称：dist/query_system/
)
