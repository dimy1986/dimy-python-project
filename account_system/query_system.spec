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
    # Bundle the templates and SQL query files into the package
    datas=[
        ("templates", "templates"),
        ("queries",   "queries"),
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
        # Inceptor / Hive connection via SSH tunnel
        "sshtunnel",
        "pyhive",
        "pyhive.hive",
        "thrift",
        "thrift.transport",
        "thrift.transport.TSocket",
        "thrift.transport.TTransport",
        "thrift.protocol",
        "thrift_sasl",
        "sasl",
        # database module
        "database",
        # 系统托盘图标
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages not needed at runtime
        "matplotlib",
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
    console=False,      # 隐藏控制台窗口，程序改由系统托盘图标驻留
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
