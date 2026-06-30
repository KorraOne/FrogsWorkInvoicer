"""Per-install secret for encrypting local auth tokens."""

import json
import os
import secrets

import storage


def _install_path():
    return os.path.join(storage.get_appdata_path(), "billing_install.json")


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
