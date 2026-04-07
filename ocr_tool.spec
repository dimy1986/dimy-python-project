# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for ocr_tool (凭证提取工具)
#
# Build command (run from this directory with venv activated):
#   pyinstaller --noconfirm --clean ocr_tool.spec
#
# After building, place the ocr_models/ folder next to the output exe:
#   dist\ocr_tool\ocr_models\ch_PP-OCRv4_det_infer\
#   dist\ocr_tool\ocr_models\ch_PP-OCRv4_rec_infer\
#   dist\ocr_tool\ocr_models\ch_ppocr_mobile_v2.0_cls_infer\

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# ── Collect paddleocr (binaries + data + submodules) ──────────────────────────
paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all('paddle')
paddleocr_datas, paddleocr_binaries, paddleocr_hiddenimports = collect_all('paddleocr')

# ── Cython data files (Utility/*.cpp etc.) referenced at runtime by paddle ────
cython_datas = collect_data_files('Cython')

# ── Additional hidden imports ─────────────────────────────────────────────────
extra_hiddenimports = [
    # paddle
    'paddle',
    'paddle.fluid',
    'paddle.nn',
    'paddle.framework',
    # paddleocr
    'paddleocr',
    'paddleocr.paddleocr',
    'paddleocr.tools',
    'paddleocr.ppocr',
    'paddleocr.ppstructure',
    # image / cv
    'cv2',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    # numpy / scipy
    'numpy',
    'skimage',
    'skimage.morphology',
    # shapely / pyclipper (used by paddleocr post-processing)
    'shapely',
    'shapely.geometry',
    'pyclipper',
    # PyMuPDF
    'fitz',
    # pandas / openpyxl (Excel output)
    'pandas',
    'openpyxl',
    'openpyxl.styles',
    'openpyxl.utils',
    # tkinter (bundled with CPython but sometimes needs explicit listing)
    'tkinter',
    'tkinter.filedialog',
    'tkinter.messagebox',
    # standard library helpers
    'importlib',
    'threading',
    'logging',
    'pathlib',
    'io',
    're',
    'imghdr',
    # packaging helpers required by paddleocr at runtime
    'setuptools',
    'pkg_resources',
    'distutils',
    'distutils.version',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=paddle_binaries + paddleocr_binaries,
    datas=paddle_datas + paddleocr_datas + cython_datas,
    hiddenimports=(
        paddle_hiddenimports
        + paddleocr_hiddenimports
        + extra_hiddenimports
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages to keep build size down
        'matplotlib',
        'scipy',
        'IPython',
        'notebook',
        'pytest',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,       # onedir mode (faster startup than onefile)
    name='ocr_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                   # Disabled: UPX can trigger antivirus false-positives
    console=False,               # GUI app — suppress console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                   # Set to 'app.ico' if you have an icon file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,                   # Disabled: UPX can trigger antivirus false-positives
    upx_exclude=[],
    name='ocr_tool',
)
