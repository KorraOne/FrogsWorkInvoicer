"""Per-install secret for encrypting local auth tokens."""

import json
import os
import secrets
import shutil

import storage

_INSTALL_FILENAME = "account_install.json"
_LEGACY_INSTALL_FILENAME = "billing_install.json"


def _install_paths():
    base = storage.get_appdata_path()
    return (
        os.path.join(base, _INSTALL_FILENAME),
        os.path.join(base, _LEGACY_INSTALL_FILENAME),
    )


def _migrate_legacy_install_file():
    new_path, old_path = _install_paths()
    if os.path.exists(new_path) or not os.path.exists(old_path):
        return
    try:
        shutil.move(old_path, new_path)
    except OSError:
        pass


def _install_path():
    _migrate_legacy_install_file()
    new_path, old_path = _install_paths()
    if os.path.exists(new_path):
        return new_path
    if os.path.exists(old_path):
        return old_path
    return new_path


def get_install_secret():
    path = _install_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        secret = data.get("install_secret")
        if secret:
            return secret
    secret = secrets.token_hex(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"install_secret": secret}, f, indent=2)
    return secret
