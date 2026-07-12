"""Sync subscription entitlements and cloud document queue from account API."""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from . import auth_store, client, entitlement_cache
import storage

log = logging.getLogger(__name__)

_SYNC_INTERVAL_SEC = 120


def sync_entitlements_from_server():
    if not auth_store.is_authenticated():
        return None
    try:
        payload = client.get_entitlements()
        entitlement_cache.update_from_entitlements(payload)
        _maybe_flush_cloud_queue()
        return payload
    except client.AccountOfflineError:
        log.warning("Entitlement sync offline")
        cached = entitlement_cache.load_cache()
        return cached if cached else None
    except Exception:
        log.exception("Entitlement sync failed")
        cached = entitlement_cache.load_cache()
        return cached if cached else None


def _maybe_flush_cloud_queue():
    from storage.context import use_cloud_provider, get_provider

    if not use_cloud_provider():
        return
    try:
        result = get_provider().flush_sync_queue()
        if result.get("flushed"):
            log.info("Cloud sync flushed %s mutations", result["flushed"])
    except Exception:
        log.exception("Cloud sync queue flush failed")


def start_background_sync():
    import threading

    def _run():
        try:
            sync_entitlements_from_server()
        except Exception:
            log.exception("Background entitlement sync failed")
        try:
            import app_platform.updates as app_update

            app_update.refresh_release_cache(force=True)
        except Exception:
            log.exception("Background update check failed")

    thread = threading.Thread(target=_run, name="frogswork-background-sync", daemon=True)
    thread.start()
    _start_cloud_sync_daemon()


def _start_cloud_sync_daemon():
    def _loop():
        while True:
            time.sleep(_SYNC_INTERVAL_SEC)
            try:
                if auth_store.is_authenticated():
                    sync_entitlements_from_server()
            except Exception:
                log.exception("Periodic cloud sync failed")

    thread = threading.Thread(target=_loop, name="frogswork-cloud-sync", daemon=True)
    thread.start()
