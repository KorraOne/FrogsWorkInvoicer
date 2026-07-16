# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_dynamic_libs

ONEFILE = os.environ.get("FROGSWORK_ONEFILE", "0") == "1"
_APP_DIR = os.path.dirname(os.path.abspath(SPEC))
_ICON_PATH = os.path.join(_APP_DIR, "assets", "app.ico")
_APP_ICON = _ICON_PATH if os.path.isfile(_ICON_PATH) else None
_RUNTIME_HOOK = os.path.join(_APP_DIR, "pyi_runtime_hook.py")

EXCLUDES = [
    "matplotlib", "numpy", "pandas", "scipy", "sklearn",
    "IPython", "ipykernel", "jupyter", "jupyter_client", "jupyter_core",
    "notebook", "nbformat", "nbconvert", "pytest", "_pytest", "py", "pluggy",
    "pygame", "cv2", "torch", "tensorflow", "zmq",
    "tornado", "wx", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "sympy", "numba", "llvmlite", "dask", "distributed",
    "bokeh", "plotly", "seaborn", "statsmodels", "openpyxl", "xlrd", "lxml",
    "sqlalchemy", "psycopg2", "pymongo", "redis", "celery", "gevent",
    "eventlet", "gunicorn", "waitress",
]

_binaries = []
for _pkg in ("pythonnet", "webview", "clr_loader"):
    try:
        _binaries += collect_dynamic_libs(_pkg)
    except Exception:
        pass

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=_binaries,
    datas=[("static", "static"), ("assets", "assets")],
    hiddenimports=[
        "cryptography",
        "cryptography.fernet",
        "_cffi_backend",
        "jwt",
        "tkinter",
        "_tkinter",
        "clr",
        "clr_loader",
        "pythonnet",
        "webview",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[_RUNTIME_HOOK] if os.path.isfile(_RUNTIME_HOOK) else [],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure, optimize=2)

if ONEFILE:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="FrogsWork",
        debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
        console=False, disable_windowed_traceback=False, argv_emulation=False,
        target_arch=None, codesign_identity=None, entitlements_file=None,
        icon=_APP_ICON,
    )
else:
    exe = EXE(
        pyz, a.scripts, [], exclude_binaries=True,
        name="FrogsWork",
        debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
        console=False, disable_windowed_traceback=False, argv_emulation=False,
        target_arch=None, codesign_identity=None, entitlements_file=None,
        icon=_APP_ICON,
    )
    coll = COLLECT(
        exe, a.binaries, a.datas,
        strip=False, upx=False, upx_exclude=[], name="FrogsWork",
    )
