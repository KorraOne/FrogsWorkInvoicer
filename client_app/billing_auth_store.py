"""Encrypted local storage for billing API tokens."""

import base64
import hashlib
import json
import os

import billing_ledger
import storage
from app_config import DEFAULT_BILLING_SERVER_URL

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None


def _auth_path():
    return os.path.join(storage.get_appdata_path(), "billing_auth.json")


def _fernet():
    if Fernet is None:
        return None
    seed = billing_ledger.get_install_secret().encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(b"auth-v1:" + seed).digest())
    return Fernet(key)


def load_auth():
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
    path = _auth_path()
    fernet = _fernet()
    if fernet:
        payload = {"_enc": fernet.encrypt(json.dumps(data).encode()).decode()}
    else:
        payload = data
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def clear_auth():
    path = _auth_path()
    if os.path.exists(path):
        os.remove(path)


def is_authenticated():
    auth = load_auth()
    return bool(auth.get("access_token"))


def get_server_url():
    auth = load_auth()
    url = auth.get("server_url") or os.environ.get(
        "BILLING_SERVER_URL", DEFAULT_BILLING_SERVER_URL
    )
    return url.rstrip("/")


def set_server_url(url):
    auth = load_auth()
    auth["server_url"] = url.rstrip("/")
    save_auth(auth)
