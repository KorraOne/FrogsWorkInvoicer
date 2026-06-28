"""PyInstaller runtime hook — pythonnet + Mark-of-the-Web (downloaded zip) fixes."""

import glob
import os
import sys


def _install_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _unblock_path(path):
    if os.name != "nt" or not path:
        return
    try:
        import ctypes

        ctypes.windll.kernel32.DeleteFileW(f"{path}:Zone.Identifier")
    except Exception:
        pass


def _unblock_tree(root):
    if os.name != "nt" or not os.path.isdir(root):
        return
    _unblock_path(root)
    for dirpath, _dirnames, filenames in os.walk(root):
        _unblock_path(dirpath)
        for name in filenames:
            _unblock_path(os.path.join(dirpath, name))


def _configure_pythonnet():
    if not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    py_dlls = sorted(glob.glob(os.path.join(meipass, "python3*.dll")))
    if py_dlls and not os.environ.get("PYTHONNET_PYDLL"):
        os.environ["PYTHONNET_PYDLL"] = py_dlls[0]


if getattr(sys, "frozen", False):
    root = _install_root()
    _unblock_path(os.path.join(root, os.path.basename(sys.executable)))
    _unblock_tree(os.path.join(root, "_internal"))
    _configure_pythonnet()
