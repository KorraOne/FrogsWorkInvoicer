# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — tuned for fast builds and fast startup.
# Use onedir (default): set INVOICEAPP_ONEFILE=1 for a single portable exe (slower cold start).

import os

ONEFILE = os.environ.get("INVOICEAPP_ONEFILE", "0") == "1"

# Packages not needed by Flask + ReportLab; excluding them shrinks the bundle and speeds analysis.
EXCLUDES = [
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "IPython",
    "ipykernel",
    "jupyter",
    "jupyter_client",
    "jupyter_core",
    "notebook",
    "nbformat",
    "nbconvert",
    "pytest",
    "_pytest",
    "py",
    "pluggy",
    "tkinter",
    "_tkinter",
    "pygame",
    "cv2",
    "torch",
    "tensorflow",
    "zmq",
    "tornado",
    "wx",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "sympy",
    "numba",
    "llvmlite",
    "dask",
    "distributed",
    "bokeh",
    "plotly",
    "seaborn",
    "statsmodels",
    "openpyxl",
    "xlrd",
    "lxml",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "redis",
    "celery",
    "gevent",
    "eventlet",
    "gunicorn",
    "waitress",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("templates", "templates"), ("static", "static")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure, optimize=2)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="InvoiceApp",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="InvoiceApp",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="InvoiceApp",
    )
