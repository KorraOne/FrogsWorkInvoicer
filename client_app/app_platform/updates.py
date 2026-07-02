"""In-app updates for the packaged FrogsWork desktop client."""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

from account import auth_store, client
from app_config import APP_VERSION

from .capabilities import is_packaged

log = logging.getLogger(__name__)

_STATE_FILE = "update_state.json"
_RESULT_FILE = "update_apply_result.json"
_LOG_FILE = "update.log"
_UPDATE_DIR_NAME = "update"
_CACHE_SECONDS = 3600
_CREATE_NO_WINDOW = 0x08000000
_ROBOCOPY_ATTEMPTS = 20
_SHUTDOWN_DELAY_SECONDS = 2.0

_cache = {"at": 0.0, "latest": None, "failed": False}


def install_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def exe_path():
    return os.path.abspath(sys.executable)


def _bootstrap_dir():
    import storage

    return storage.get_bootstrap_dir()


def _update_dir():
    return os.path.join(_bootstrap_dir(), _UPDATE_DIR_NAME)


def _state_path():
    return os.path.join(_bootstrap_dir(), _STATE_FILE)


def _result_path():
    return os.path.join(_bootstrap_dir(), _RESULT_FILE)


def _log_path():
    return os.path.join(_bootstrap_dir(), _LOG_FILE)


def _updater_script_path():
    return os.path.join(_update_dir(), "apply-update.ps1")


def append_update_log(message):
    try:
        os.makedirs(_bootstrap_dir(), exist_ok=True)
        line = f"{datetime.now(timezone.utc).isoformat()} {message}\n"
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        log.exception("Could not write update log")


def _read_state_file():
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state_file(data):
    os.makedirs(_bootstrap_dir(), exist_ok=True)
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _merge_apply_result():
    path = _result_path()
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8-sig") as f:
            result = json.load(f)
        os.remove(path)
    except (OSError, json.JSONDecodeError):
        log.exception("Could not read update apply result")
        return

    state = _read_state_file()
    version = (result.get("version") or "").strip()
    if result.get("ok"):
        state.pop("last_apply_failed", None)
        state.pop("last_apply_error", None)
        if version:
            state["last_apply_version"] = version
    else:
        state["last_apply_failed"] = True
        state["last_apply_error"] = (result.get("error") or "Update failed").strip()
        if version:
            state["last_apply_version"] = version
    _write_state_file(state)


def load_state():
    _merge_apply_result()
    return _read_state_file()


def save_state(data):
    os.makedirs(_bootstrap_dir(), exist_ok=True)
    _write_state_file(data)


def parse_version(raw):
    parts = [int(n) for n in re.findall(r"\d+", str(raw or "0"))]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def version_less(left, right):
    return parse_version(left) < parse_version(right)


def fetch_latest_release():
    if not client.check_server_available():
        return None
    url = auth_store.get_server_url().rstrip("/") + "/releases/latest"
    req = urllib.request.Request(url, headers=client.api_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204:
                return None
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 204:
            return None
        raise
    except Exception:
        log.exception("Failed to fetch release info")
        return None

    version = (data.get("version") or "").strip()
    download_url = (data.get("download_url") or "").strip()
    if not version or not download_url:
        return None
    return {
        "version": version,
        "download_url": download_url,
        "sha256": (data.get("sha256") or "").strip().lower(),
        "notes": (data.get("notes") or "").strip(),
    }


def refresh_release_cache(force=False):
    now = time.time()
    cache_fresh = _cache["at"] and (now - _cache["at"]) < _CACHE_SECONDS
    if not force and cache_fresh:
        return _cache["latest"]

    latest = None
    failed = False
    try:
        latest = fetch_latest_release()
    except Exception:
        log.exception("Release check failed")
        failed = True

    _cache["at"] = now
    _cache["latest"] = latest
    _cache["failed"] = failed

    if latest:
        state = load_state()
        state["last_seen_version"] = latest["version"]
        save_state(state)
    return latest


def _maybe_refresh_release_cache_async():
    now = time.time()
    if _cache["at"] and (now - _cache["at"]) < _CACHE_SECONDS:
        return
    threading.Thread(
        target=lambda: refresh_release_cache(force=True),
        daemon=True,
        name="update-cache-refresh",
    ).start()


def get_apply_failure():
    """Return failed apply info when still behind the target version."""
    state = load_state()
    if not state.get("last_apply_failed"):
        return None
    target = (state.get("last_apply_version") or "").strip()
    if not target or not version_less(APP_VERSION, target):
        return None
    return {
        "version": target,
        "error": (state.get("last_apply_error") or "").strip(),
        "started_at": state.get("last_apply_started_at") or "",
    }


def get_pending_update(force_check=False):
    if not is_packaged():
        return None
    if force_check:
        refresh_release_cache(force=True)
    else:
        _maybe_refresh_release_cache_async()

    latest = _cache["latest"]
    if not latest or not version_less(APP_VERSION, latest["version"]):
        return None

    state = load_state()
    dismissed = (state.get("dismissed_version") or "").strip()
    apply_failed = get_apply_failure()
    banner_hidden = dismissed == latest["version"] and not apply_failed
    return {
        **latest,
        "current_version": APP_VERSION,
        "banner_hidden": banner_hidden,
        "apply_failed": bool(apply_failed),
        "apply_failed_error": apply_failed.get("error") if apply_failed else "",
    }


def dismiss_update(version):
    state = load_state()
    state["dismissed_version"] = version
    save_state(state)


def mark_apply_started(version):
    state = load_state()
    if (state.get("dismissed_version") or "").strip() == version:
        state.pop("dismissed_version", None)
    state["last_apply_version"] = version
    state["last_apply_started_at"] = datetime.now(timezone.utc).isoformat()
    state.pop("last_apply_failed", None)
    state.pop("last_apply_error", None)
    save_state(state)


def _record_apply_failure(version, error):
    append_update_log(f"Update failed: {error}")
    state = load_state()
    state["last_apply_failed"] = True
    state["last_apply_error"] = error
    if version:
        state["last_apply_version"] = version
    save_state(state)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(url, dest):
    req = urllib.request.Request(url, headers=client.api_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def _extract_zip(zip_path, dest_dir):
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


def _find_update_root(extracted_dir):
    if os.path.isfile(os.path.join(extracted_dir, "FrogsWork.exe")):
        return extracted_dir
    for name in os.listdir(extracted_dir):
        path = os.path.join(extracted_dir, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "FrogsWork.exe")):
            return path
    raise RuntimeError("Update package did not contain FrogsWork.exe.")


def _ps1_escape(value):
    return str(value).replace("'", "''")


def _build_updater_script(*, pid_to_wait, staging_root, install, target_exe, version):
    log_path = _log_path()
    result_path = _result_path()
    return f"""$ErrorActionPreference = 'Continue'
$pidToWait = {pid_to_wait}
$staging = '{_ps1_escape(staging_root)}'
$install = '{_ps1_escape(install)}'
$exe = '{_ps1_escape(target_exe)}'
$version = '{_ps1_escape(version)}'
$logPath = '{_ps1_escape(log_path)}'
$resultPath = '{_ps1_escape(result_path)}'

function Write-UpdateLog {{
    param([string]$Message)
    try {{
        $line = "$(Get-Date -Format o) [updater] $Message"
        Add-Content -Path $logPath -Value $line -Encoding UTF8
    }} catch {{}}
}}

function Write-ApplyResult {{
    param([bool]$Ok, [string]$ErrorMsg)
    try {{
        @{{
            ok = $Ok
            version = $version
            error = $ErrorMsg
        }} | ConvertTo-Json | Set-Content -Path $resultPath -Encoding UTF8
    }} catch {{
        Write-UpdateLog "Could not write apply result: $_"
    }}
}}

function Stop-InstallProcesses {{
    param([string]$InstallDir, [int]$MainPid)
    try {{
        Get-CimInstance Win32_Process | Where-Object {{
            $_.ProcessId -ne $MainPid -and $_.ExecutablePath -and (
                $_.ExecutablePath.StartsWith($InstallDir, [System.StringComparison]::OrdinalIgnoreCase) -or
                ($_.Name -eq 'msedgewebview2.exe' -and $_.CommandLine -like "*$InstallDir*")
            )
        }} | ForEach-Object {{
            Write-UpdateLog "Stopping PID $($_.ProcessId) $($_.Name)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }}
    }} catch {{
        Write-UpdateLog "Stop-InstallProcesses: $_"
    }}
}}

Write-UpdateLog "Updater started for version $version (wait pid $pidToWait)"
try {{
    Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue
}} catch {{
    Write-UpdateLog "Wait-Process: $_"
}}
Start-Sleep -Seconds 3
Stop-InstallProcesses -InstallDir $install -MainPid $pidToWait
Start-Sleep -Seconds 2

$copyOk = $false
$lastCode = 0
for ($i = 1; $i -le {_ROBOCOPY_ATTEMPTS}; $i++) {{
    Write-UpdateLog "robocopy attempt $i"
    # /Z is restartable mode. Avoid /B or /ZB because they require "Backup and Restore Files" rights.
    $out = & robocopy $staging $install /MIR /Z /R:3 /W:2 /NFL /NDL /NJH /NJS /NP 2>&1
    $lastCode = $LASTEXITCODE
    Write-UpdateLog "robocopy exit $lastCode"
    try {{
        $tail = $out | Select-Object -Last 8
        foreach ($line in $tail) {{
            if ($line) {{ Write-UpdateLog "robocopy out: $line" }}
        }}
    }} catch {{}}
    if ($lastCode -lt 8) {{
        $copyOk = $true
        break
    }}
    Stop-InstallProcesses -InstallDir $install -MainPid $pidToWait
    Start-Sleep -Seconds 2
}}

if (-not $copyOk) {{
    Write-ApplyResult $false "robocopy failed after {_ROBOCOPY_ATTEMPTS} attempts (exit $lastCode)"
    Write-UpdateLog "Update failed"
    exit 1
}}

Write-UpdateLog "Starting $exe"
Start-Process -FilePath $exe -WorkingDirectory $install
Write-ApplyResult $true ""
Write-UpdateLog "Update succeeded"
"""


def _updater_vbs_path():
    return os.path.join(_update_dir(), "launch-updater.vbs")


def _launch_updater(script_path):
    vbs_path = _updater_vbs_path()
    ps_quoted = script_path.replace('"', '""')
    vbs_content = (
        'Set sh = CreateObject("Wscript.Shell")\r\n'
        f'sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{ps_quoted}""", 0, False\r\n'
    )
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)
    append_update_log(f"Launching updater (hidden): {script_path}")
    proc = subprocess.Popen(
        ["wscript.exe", "//B", "//Nologo", vbs_path],
        cwd=_bootstrap_dir(),
        creationflags=_CREATE_NO_WINDOW,
        close_fds=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    append_update_log(f"Updater launcher pid {proc.pid}")


def _prepare_update_package(release):
    version = (release.get("version") or "").strip()
    update_dir = _update_dir()
    staging_root = os.path.join(update_dir, "staging")
    extracted = os.path.join(update_dir, "extracted")
    zip_path = os.path.join(update_dir, "update.zip")

    if os.path.isdir(update_dir):
        shutil.rmtree(update_dir, ignore_errors=True)
    os.makedirs(staging_root, exist_ok=True)
    os.makedirs(extracted, exist_ok=True)

    append_update_log(f"Update {version}: downloading {release['download_url']}")
    _download_file(release["download_url"], zip_path)

    expected = (release.get("sha256") or "").lower()
    if expected:
        digest = _sha256_file(zip_path)
        if digest != expected:
            raise RuntimeError("Update file failed integrity check.")
        append_update_log(f"Update {version}: sha256 ok")

    append_update_log(f"Update {version}: extracting")
    _extract_zip(zip_path, extracted)
    source_root = _find_update_root(extracted)
    shutil.copytree(source_root, staging_root, dirs_exist_ok=True)
    append_update_log(f"Update {version}: staged at {staging_root}")
    return staging_root


def _run_apply_update(release, shutdown_callback):
    if not is_packaged():
        raise RuntimeError("Updates are only available in the packaged app.")

    version = (release.get("version") or "").strip()
    mark_apply_started(version)
    append_update_log(f"Update {version}: apply started (pid {os.getpid()})")

    try:
        staging_root = _prepare_update_package(release)
        install = install_dir()
        target_exe = exe_path()
        script_path = _updater_script_path()
        os.makedirs(_update_dir(), exist_ok=True)
        script = _build_updater_script(
            pid_to_wait=os.getpid(),
            staging_root=staging_root,
            install=install,
            target_exe=target_exe,
            version=version,
        )
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        append_update_log(f"Update {version}: updater script written to {script_path}")

        _launch_updater(script_path)
        time.sleep(_SHUTDOWN_DELAY_SECONDS)
        append_update_log(f"Update {version}: shutting down app")
        shutdown_callback()
    except Exception as exc:
        _record_apply_failure(version, str(exc))
        raise


def start_apply_update(release, shutdown_callback):
    """Download in a worker thread; return immediately for UI feedback."""
    if not is_packaged():
        raise RuntimeError("Updates are only available in the packaged app.")

    version = (release.get("version") or "").strip()
    append_update_log(f"Update {version}: queued")

    def _worker():
        try:
            _run_apply_update(release, shutdown_callback)
        except Exception:
            log.exception("Background update failed")

    threading.Thread(target=_worker, name="frogswork-update", daemon=False).start()


def apply_update(release, shutdown_callback):
    """Blocking apply (tests / legacy callers)."""
    _run_apply_update(release, shutdown_callback)
