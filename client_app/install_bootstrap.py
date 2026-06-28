"""First-run install location helper for the packaged Windows client."""

import json
import os
import subprocess
import sys

from app_config import APP_BRAND_NAME, APP_DATA_DIR_NAME

_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008
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


def _inform(title, message):
    if os.name != "nt":
        return
    import ctypes

    MB_OK = 0x00000000
    MB_ICONINFORMATION = 0x00000040
    ctypes.windll.user32.MessageBoxW(0, message, title, MB_OK | MB_ICONINFORMATION)


def _show_error(message):
    if os.name != "nt":
        return
    import ctypes

    MB_OK = 0x00000000
    MB_ICONERROR = 0x00000010
    ctypes.windll.user32.MessageBoxW(0, message, APP_BRAND_NAME, MB_OK | MB_ICONERROR)


def _ps1_escape(value):
    return str(value).replace("'", "''")


def _spawn_relocate_script(src, dst, pid, create_shortcut):
    import tempfile

    tmp = tempfile.mkdtemp(prefix="FrogsWork-install-")
    script_path = os.path.join(tmp, "relocate.ps1")
    exe_name = os.path.basename(sys.executable)
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    script = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$src = '{_ps1_escape(src)}'
$dst = '{_ps1_escape(dst)}'
$exe = Join-Path $dst '{_ps1_escape(exe_name)}'
$desktop = '{_ps1_escape(desktop)}'
$createShortcut = ${str(create_shortcut).lower()}
try {{ Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Seconds 2
New-Item -ItemType Directory -Force -Path $dst | Out-Null
& robocopy $src $dst /MIR /R:5 /W:2 /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) {{ exit 1 }}
if ($createShortcut -and (Test-Path $desktop)) {{
    $shell = New-Object -ComObject WScript.Shell
    $link = Join-Path $desktop '{_ps1_escape(APP_BRAND_NAME)}.lnk'
    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = $dst
    $shortcut.Save()
}}
Start-Process -FilePath $exe
"""
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_path,
        ],
        creationflags=_CREATE_NO_WINDOW | _DETACHED_PROCESS,
        close_fds=True,
    )


def _offer_desktop_shortcut():
    state = _load_state()
    if state.get("desktop_shortcut_offered"):
        return

    exe = sys.executable
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    if not os.path.isdir(desktop):
        state["desktop_shortcut_offered"] = True
        _save_state(state)
        return

    message = (
        f"Add a Desktop shortcut for {APP_BRAND_NAME}?\n\n"
        "You can always pin the app to your taskbar from the Start menu later."
    )
    if _ask_yes_no(f"{APP_BRAND_NAME} shortcut", message):
        try:
            import tempfile

            tmp = tempfile.mkdtemp(prefix="FrogsWork-shortcut-")
            script_path = os.path.join(tmp, "shortcut.ps1")
            script = f"""$shell = New-Object -ComObject WScript.Shell
$link = Join-Path '{_ps1_escape(desktop)}' '{_ps1_escape(APP_BRAND_NAME)}.lnk'
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = '{_ps1_escape(exe)}'
$shortcut.WorkingDirectory = '{_ps1_escape(install_dir())}'
$shortcut.Save()
"""
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script)
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
                creationflags=_CREATE_NO_WINDOW,
                check=False,
            )
            state["desktop_shortcut_created"] = True
        except Exception:
            pass

    state["desktop_shortcut_offered"] = True
    _save_state(state)


def maybe_relocate_install():
    if os.name != "nt" or not _is_packaged():
        return

    current = _norm(install_dir())
    target = recommended_install_dir()
    if not target:
        return

    if current == _norm(target):
        _offer_desktop_shortcut()
        return

    create_shortcut = _ask_yes_no(
        f"Install {APP_BRAND_NAME}",
        f"Create a Desktop shortcut for {APP_BRAND_NAME}?",
    )

    _inform(
        f"Installing {APP_BRAND_NAME}",
        (
            f"Moving to:\n{target}\n\n"
            "The app will close and restart from there in a few seconds."
        ),
    )

    try:
        _spawn_relocate_script(current, target, os.getpid(), create_shortcut)
    except Exception:
        _show_error(
            f"Could not start install to:\n{target}\n\n"
            f"Extract the FrogsWork folder to that path manually, then run FrogsWork.exe."
        )
        return

    sys.exit(0)
