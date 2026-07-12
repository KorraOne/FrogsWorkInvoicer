"""Resolve active storage provider (local vs cloud)."""

from __future__ import annotations

import logging

from account import entitlement_cache
from storage.providers.cloud import CloudProvider
from storage.providers.local import LocalProvider
from storage.settings import load_settings

log = logging.getLogger(__name__)

_local_provider: LocalProvider | None = None
_cloud_provider: CloudProvider | None = None


def get_storage_tier() -> str:
    """Return entitlement storage tier: local or cloud."""
    cache = entitlement_cache.load_cache()
    tier = (cache.get("storage_tier") or "local").strip().lower()
    return tier if tier in ("local", "cloud") else "local"


def get_storage_mode() -> str:
    """Return client storage mode from settings (desktop)."""
    settings = load_settings()
    mode = (settings.get("storage_mode") or "local").strip().lower()
    tier = get_storage_tier()
    if tier != "cloud":
        return "local"
    return mode if mode in ("local", "cloud") else "local"


def set_storage_mode(mode: str) -> None:
    from storage.settings import save_settings

    settings = load_settings()
    settings["storage_mode"] = mode
    save_settings(settings)


def cloud_entitled() -> bool:
    return get_storage_tier() == "cloud" and entitlement_cache.subscription_active_with_grace()


def use_cloud_provider() -> bool:
    return cloud_entitled() and get_storage_mode() == "cloud"


def get_provider():
    """Return the active StorageProvider for this session."""
    global _local_provider, _cloud_provider
    if use_cloud_provider():
        if _cloud_provider is None:
            _cloud_provider = CloudProvider()
        return _cloud_provider
    if _local_provider is None:
        _local_provider = LocalProvider()
    return _local_provider


def reset_providers() -> None:
    """Clear cached provider instances (e.g. after mode switch)."""
    global _local_provider, _cloud_provider
    _local_provider = None
    _cloud_provider = None


def active_provider():
    """Return cloud provider when cloud mode is active, else None (use local JSON)."""
    if use_cloud_provider():
        return get_provider()
    return None
