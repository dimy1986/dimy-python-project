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

# ── Collect packages that have C extensions or whose dist-info is queried ─────
# by paddleocr at runtime via importlib.metadata / pkg_resources.
# Using collect_all() ensures both the compiled extension (.pyd/.so) AND the
# package metadata (.dist-info directory) end up inside _internal/, preventing
# PackageNotFoundError / ModuleNotFoundError at startup.
imageio_datas,   imageio_binaries,   imageio_hiddenimports   = collect_all('imageio')
lmdb_datas,      lmdb_binaries,      lmdb_hiddenimports      = collect_all('lmdb')
skimage_datas,   skimage_binaries,   skimage_hiddenimports   = collect_all('skimage')
pyclipper_datas, pyclipper_binaries, pyclipper_hiddenimports = collect_all('pyclipper')
shapely_datas,   shapely_binaries,   shapely_hiddenimports   = collect_all('shapely')

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
    'scipy',
    'scipy.ndimage',
    'scipy.ndimage._filters',
    'scipy.ndimage._interpolation',
    'scipy.spatial',
    'scipy.special',
    # imgaug (used by paddleocr data augmentation pipelines)
    'imgaug',
    'imgaug.augmenters',
    # lmdb, shapely, pyclipper, skimage — covered by collect_all() above;
    # list top-level names here as a belt-and-suspenders guard.
    'lmdb',
    'shapely',
    'shapely.geometry',
    'pyclipper',
    'skimage',
    'skimage.morphology',
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
    binaries=paddle_binaries + paddleocr_binaries + imageio_binaries + lmdb_binaries + skimage_binaries + pyclipper_binaries + shapely_binaries,
    datas=paddle_datas + paddleocr_datas + imageio_datas + lmdb_datas + skimage_datas + pyclipper_datas + shapely_datas + cython_datas,
    hiddenimports=(
        paddle_hiddenimports
        + paddleocr_hiddenimports
        + imageio_hiddenimports
        + lmdb_hiddenimports
        + skimage_hiddenimports
        + pyclipper_hiddenimports
        + shapely_hiddenimports
        + extra_hiddenimports
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages to keep build size down
        'matplotlib',
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
