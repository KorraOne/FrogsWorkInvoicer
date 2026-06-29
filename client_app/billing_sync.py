"""Background sync of billing usage from server (explicit points only)."""

import json
import logging
import os
import time
from decimal import Decimal

import billing_auth_store
import billing_client
import storage

log = logging.getLogger(__name__)

_CACHE_FILE = "usage_cache.json"


def _cache_path():
    return os.path.join(storage.get_bootstrap_dir(), _CACHE_FILE)


def _serialize_usage(usage):
    out = {}
    for key, value in usage.items():
        if isinstance(value, Decimal):
            out[key] = str(value)
        else:
            out[key] = value
    return out


def _deserialize_usage(data):
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    for key in (
        "month_total_ex_gst",
        "fee_so_far",
        "projected_fee",
        "fee_delta",
        "free_remaining",
        "over_by",
        "cap_amount_ex_gst",
    ):
        if key in out and out[key] is not None:
            try:
                out[key] = Decimal(str(out[key]))
            except Exception:
                pass
    return out


def save_usage_cache(usage):
    payload = {
        "synced_at": time.time(),
        "usage": _serialize_usage(usage),
    }
    os.makedirs(storage.get_bootstrap_dir(), exist_ok=True)
    with open(_cache_path(), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_usage_cache():
    path = _cache_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    usage = _deserialize_usage(raw.get("usage"))
    if not usage:
        return None
    return {"synced_at": raw.get("synced_at"), "usage": usage}


def sync_usage_from_server():
    """Fetch usage from billing API and cache locally. No-op when signed out."""
    if not billing_auth_store.is_authenticated():
        return None
    try:
        usage = billing_client.get_usage()
        save_usage_cache(usage)
        return usage
    except Exception:
        log.exception("Usage sync failed")
        cached = load_usage_cache()
        return cached["usage"] if cached else None


def start_background_sync():
    """Refresh usage and update metadata without blocking page loads."""

    def _run():
        try:
            sync_usage_from_server()
        except Exception:
            log.exception("Background usage sync failed")
        try:
            import app_update

            if app_update.is_packaged():
                app_update.refresh_release_cache(force=True)
        except Exception:
            log.exception("Background update check failed")

    import threading

    threading.Thread(target=_run, daemon=True, name="frogswork-background-sync").start()
