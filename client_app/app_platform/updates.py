"""In-app updates for the packaged FrogsWork desktop client."""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
_CACHE_SECONDS = 3600
_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008
_ROBOCOPY_ATTEMPTS = 15

_cache = {"at": 0.0, "latest": None, "failed": False}


def install_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def exe_path():
    return os.path.abspath(sys.executable)


def _bootstrap_dir():
    import storage

    return storage.get_bootstrap_dir()


def _state_path():
    return os.path.join(_bootstrap_dir(), _STATE_FILE)


def _result_path():
    return os.path.join(_bootstrap_dir(), _RESULT_FILE)


def _log_path():
    return os.path.join(_bootstrap_dir(), _LOG_FILE)


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
        with open(path, encoding="utf-8") as f:
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
    if not force and cache_fresh and _cache["latest"] is not None:
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
    elif _cache["latest"] is None or (time.time() - _cache["at"]) >= _CACHE_SECONDS:
        refresh_release_cache(force=True)

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
    return f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid_to_wait}
$staging = '{_ps1_escape(staging_root)}'
$install = '{_ps1_escape(install)}'
$exe = '{_ps1_escape(target_exe)}'
$version = '{_ps1_escape(version)}'
$logPath = '{_ps1_escape(log_path)}'
$resultPath = '{_ps1_escape(result_path)}'

function Write-UpdateLog {{
    param([string]$Message)
    $line = "$(Get-Date -Format o) $Message"
    Add-Content -Path $logPath -Value $line -Encoding UTF8
}}

function Write-ApplyResult {{
    param([bool]$Ok, [string]$ErrorMsg)
    @{{
        ok = $Ok
        version = $version
        error = $ErrorMsg
    }} | ConvertTo-Json | Set-Content -Path $resultPath -Encoding UTF8
}}

function Stop-FrogsWorkChildren {{
    param([string]$InstallDir, [int]$MainPid)
    try {{
        Get-CimInstance Win32_Process | Where-Object {{
            $_.ParentProcessId -eq $MainPid -and $_.ExecutablePath -like "$InstallDir*"
        }} | ForEach-Object {{
            Write-UpdateLog "Stopping child PID $($_.ProcessId) $($_.Name)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }}
    }} catch {{
        Write-UpdateLog "Stop-FrogsWorkChildren: $_"
    }}
}}

Write-UpdateLog "Updater started for version $version (pid $pidToWait)"
try {{
    Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue
}} catch {{
    Write-UpdateLog "Wait-Process: $_"
}}
Start-Sleep -Seconds 2
Stop-FrogsWorkChildren -InstallDir $install -MainPid $pidToWait

Get-Process -Name 'FrogsWork' -ErrorAction SilentlyContinue | Where-Object {{
    $_.Path -and $_.Path.StartsWith($install, [System.StringComparison]::OrdinalIgnoreCase)
}} | ForEach-Object {{
    if ($_.Id -ne $pidToWait) {{
        Write-UpdateLog "Stopping FrogsWork PID $($_.Id)"
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }}
}}
Start-Sleep -Seconds 1

$copyOk = $false
$lastCode = 0
for ($i = 1; $i -le {_ROBOCOPY_ATTEMPTS}; $i++) {{
    Write-UpdateLog "robocopy attempt $i"
    & robocopy $staging $install /MIR /ZB /R:3 /W:2 /NFL /NDL /NJH /NJS /NP
    $lastCode = $LASTEXITCODE
    Write-UpdateLog "robocopy exit $lastCode"
    if ($lastCode -lt 8) {{
        $copyOk = $true
        break
    }}
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


def apply_update(release, shutdown_callback):
    if not is_packaged():
        raise RuntimeError("Updates are only available in the packaged app.")

    version = (release.get("version") or "").strip()
    mark_apply_started(version)

    tmp = tempfile.mkdtemp(prefix="FrogsWork-update-")
    zip_path = os.path.join(tmp, "update.zip")
    extracted = os.path.join(tmp, "extracted")
    os.makedirs(extracted, exist_ok=True)

    try:
        _download_file(release["download_url"], zip_path)
        expected = (release.get("sha256") or "").lower()
        if expected:
            digest = _sha256_file(zip_path)
            if digest != expected:
                raise RuntimeError("Update file failed integrity check.")

        _extract_zip(zip_path, extracted)
        staging_root = _find_update_root(extracted)
        install = install_dir()
        target_exe = exe_path()
        updater_path = os.path.join(tmp, "apply-update.ps1")
        script = _build_updater_script(
            pid_to_wait=os.getpid(),
            staging_root=staging_root,
            install=install,
            target_exe=target_exe,
            version=version,
        )
        with open(updater_path, "w", encoding="utf-8") as f:
            f.write(script)

        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                updater_path,
            ],
            creationflags=_CREATE_NO_WINDOW | _DETACHED_PROCESS,
            close_fds=True,
        )
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        state = load_state()
        state["last_apply_failed"] = True
        state["last_apply_error"] = "Download or prepare failed before restart"
        if version:
            state["last_apply_version"] = version
        save_state(state)
        raise

    shutdown_callback()
