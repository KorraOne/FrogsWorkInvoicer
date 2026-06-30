"""Cached subscription status for offline access with grace period."""

import json
import os
from datetime import datetime, timezone

import storage
from app_config import (
    SUBSCRIPTION_OFFLINE_GRACE_DAYS,
    SUBSCRIPTION_OFFLINE_REMINDER_DAYS,
)


def _cache_path():
    return os.path.join(storage.get_appdata_path(), "entitlement_cache.json")


def load_cache():
    path = _cache_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_cache(data):
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def clear_cache():
    path = _cache_path()
    if os.path.exists(path):
        os.remove(path)


def _parse_iso(value):
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def days_since_verified():
    cache = load_cache()
    verified = _parse_iso(cache.get("last_verified_at"))
    if not verified:
        return None
    now = datetime.now(timezone.utc)
    if verified.tzinfo is None:
        verified = verified.replace(tzinfo=timezone.utc)
    return (now - verified).days


def update_from_entitlements(payload):
    cache = load_cache()
    cache["active"] = bool(payload.get("active"))
    cache["status"] = payload.get("status", "")
    cache["last_verified_at"] = datetime.now(timezone.utc).isoformat()
    cache["access_until"] = payload.get("access_until") or payload.get("current_period_end")
    cache["current_period_end"] = cache["access_until"]
    cache["canceling"] = bool(payload.get("canceling"))
    cache["portal_url"] = payload.get("portal_url")
    cache["plan_interval"] = payload.get("plan_interval")
    save_cache(cache)
    return cache


def subscription_active_with_grace():
    cache = load_cache()
    if not cache.get("active"):
        return False
    days = days_since_verified()
    if days is None:
        return False
    return days <= SUBSCRIPTION_OFFLINE_GRACE_DAYS


def sync_status():
    """Return offline sync UX state for subscribed users."""
    cache = load_cache()
    if not cache.get("active"):
        return "inactive"
    days = days_since_verified()
    if days is None:
        return "never_verified"
    if days >= SUBSCRIPTION_OFFLINE_GRACE_DAYS:
        return "grace_expired"
    if days >= SUBSCRIPTION_OFFLINE_REMINDER_DAYS:
        return "reminder"
    return "ok"
