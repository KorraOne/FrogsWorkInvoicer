"""First-run install location helper for the packaged Windows client."""

import json
import os
import shutil
import subprocess
import sys

from app_config import APP_BRAND_NAME, APP_DATA_DIR_NAME

_CREATE_NO_WINDOW = 0x08000000
_STATE_FILE = "install_state.json"


def _is_packaged():
    return getattr(sys, "frozen", False)


def install_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def recommended_install_dir():
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        return ""
    return os.path.join(local, "Programs", APP_DATA_DIR_NAME)


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _state_path():
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return ""
    return os.path.join(appdata, APP_DATA_DIR_NAME, _STATE_FILE)


def _load_state():
    path = _state_path()
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(data):
    path = _state_path()
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _ask_yes_no(title, message):
    if os.name != "nt":
        return False
    import ctypes

    MB_YESNO = 0x00000004
    MB_ICONQUESTION = 0x00000020
    IDYES = 6
    result = ctypes.windll.user32.MessageBoxW(0, message, title, MB_YESNO | MB_ICONQUESTION)
    return result == IDYES


def _ps1_escape(value):
    return str(value).replace("'", "''")


def _copy_install(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(dst):
        script = f"""$ErrorActionPreference = 'Stop'
& robocopy '{_ps1_escape(src)}' '{_ps1_escape(dst)}' /MIR /R:3 /W:1 /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) {{ exit 1 }}
"""
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            creationflags=_CREATE_NO_WINDOW,
            check=False,
        )
        if proc.returncode >= 8:
            raise RuntimeError("Could not copy FrogsWork to the install folder.")
        return
    shutil.copytree(src, dst)


def maybe_relocate_install():
    if os.name != "nt" or not _is_packaged():
        return

    current = _norm(install_dir())
    target = recommended_install_dir()
    if not target or current == _norm(target):
        return

    state = _load_state()
    declined = {_norm(p) for p in state.get("declined_install_from", [])}
    if current in declined:
        return

    message = (
        f"{APP_BRAND_NAME} works best when installed to:\n\n"
        f"{target}\n\n"
        "Install there now? (Recommended — keeps your Desktop/Downloads tidy and "
        "lets in-app updates work reliably.)"
    )
    if not _ask_yes_no(f"Install {APP_BRAND_NAME}", message):
        declined.add(current)
        state["declined_install_from"] = sorted(declined)
        _save_state(state)
        return

    try:
        _copy_install(current, target)
    except Exception:
        import ctypes

        MB_OK = 0x00000000
        MB_ICONERROR = 0x00000010
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Could not install to:\n{target}\n\nYou can extract the app to that folder manually.",
            APP_BRAND_NAME,
            MB_OK | MB_ICONERROR,
        )
        return

    exe_name = os.path.basename(sys.executable)
    new_exe = os.path.join(target, exe_name)
    subprocess.Popen([new_exe], close_fds=True, creationflags=_CREATE_NO_WINDOW)
    sys.exit(0)
