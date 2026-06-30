"""Encrypted local storage for account API tokens."""

import base64
import hashlib
import json
import os
import shutil

import storage
from app_config import DEFAULT_ACCOUNT_API_URL

from .install_secret import get_install_secret

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

_AUTH_FILENAME = "account_auth.json"
_LEGACY_AUTH_FILENAME = "billing_auth.json"


def _auth_paths():
    base = storage.get_appdata_path()
    return (
        os.path.join(base, _AUTH_FILENAME),
        os.path.join(base, _LEGACY_AUTH_FILENAME),
    )


def _auth_path():
    new_path, old_path = _auth_paths()
    if os.path.exists(new_path):
        return new_path
    if os.path.exists(old_path):
        return old_path
    return new_path


def _migrate_legacy_auth_file():
    new_path, old_path = _auth_paths()
    if os.path.exists(new_path) or not os.path.exists(old_path):
        return
    try:
        shutil.move(old_path, new_path)
    except OSError:
        pass


def _fernet():
    if Fernet is None:
        return None
    seed = get_install_secret().encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(b"auth-v1:" + seed).digest())
    return Fernet(key)


def load_auth():
    _migrate_legacy_auth_file()
    path = _auth_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    fernet = _fernet()
    if fernet and raw.get("_enc"):
        try:
            decrypted = fernet.decrypt(raw["_enc"].encode()).decode()
            return json.loads(decrypted)
        except Exception:
            return {}
    return raw


def save_auth(data):
    new_path, _old_path = _auth_paths()
    fernet = _fernet()
    if fernet:
        payload = {"_enc": fernet.encrypt(json.dumps(data).encode()).decode()}
    else:
        payload = data
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def clear_auth():
    for path in _auth_paths():
        if os.path.exists(path):
            os.remove(path)


def is_authenticated():
    auth = load_auth()
    return bool(auth.get("access_token"))


def get_server_url():
    env_url = (
        os.environ.get("FROGSWORK_ACCOUNT_API_URL", "").strip()
        or os.environ.get("BILLING_SERVER_URL", "").strip()
        or os.environ.get("FROGSWORK_BILLING_URL", "").strip()
    )
    if env_url:
        return env_url.rstrip("/")
    auth = load_auth()
    url = auth.get("server_url") or DEFAULT_ACCOUNT_API_URL
    return url.rstrip("/")


def set_server_url(url):
    auth = load_auth()
    auth["server_url"] = url.rstrip("/")
    save_auth(auth)
