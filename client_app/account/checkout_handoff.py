"""Hand off Stripe checkout session from external browser back to the desktop app."""

import json
import os
from datetime import datetime, timezone

import storage


def _path():
    return os.path.join(storage.get_appdata_path(), "pending_stripe_checkout.json")


def save_pending_checkout(session_id):
    session_id = (session_id or "").strip()
    if not session_id.startswith("cs_"):
        return False
    os.makedirs(storage.get_appdata_path(), exist_ok=True)
    payload = {
        "session_id": session_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return True


def load_pending_checkout():
    path = _path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        session_id = (data.get("session_id") or "").strip()
        if session_id.startswith("cs_"):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def clear_pending_checkout():
    path = _path()
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def consume_pending_checkout():
    data = load_pending_checkout()
    if data:
        clear_pending_checkout()
    return data
