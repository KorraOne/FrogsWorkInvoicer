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

from account import auth_store, client
from app_config import APP_VERSION

from .capabilities import is_packaged

log = logging.getLogger(__name__)

_STATE_FILE = "update_state.json"
_CACHE_SECONDS = 3600
_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008

_cache = {"at": 0.0, "latest": None, "failed": False}


def install_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def exe_path():
    return os.path.abspath(sys.executable)


def _state_path():
    import storage

    return os.path.join(storage.get_bootstrap_dir(), _STATE_FILE)


def load_state():
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(data):
    import storage

    os.makedirs(storage.get_bootstrap_dir(), exist_ok=True)
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


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
    if not force and (now - _cache["at"]) < _CACHE_SECONDS:
        return _cache["latest"]

    if not force:
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


def get_pending_update(force_check=False):
    if not is_packaged():
        return None
    if force_check:
        refresh_release_cache(force=True)
    latest = _cache["latest"]
    if not latest or not version_less(APP_VERSION, latest["version"]):
        return None
    dismissed = (load_state().get("dismissed_version") or "").strip()
    return {
        **latest,
        "current_version": APP_VERSION,
        "banner_hidden": dismissed == latest["version"],
    }


def dismiss_update(version):
    state = load_state()
    state["dismissed_version"] = version
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


def apply_update(release, shutdown_callback):
    if not is_packaged():
        raise RuntimeError("Updates are only available in the packaged app.")

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
        script = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {os.getpid()}
$staging = '{_ps1_escape(staging_root)}'
$install = '{_ps1_escape(install)}'
$exe = '{_ps1_escape(target_exe)}'
try {{ Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Seconds 2
& robocopy $staging $install /MIR /R:5 /W:2 /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) {{ exit 1 }}
Start-Process -FilePath $exe
"""
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
        raise

    shutdown_callback()
