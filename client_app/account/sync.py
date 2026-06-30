"""Sync subscription entitlements from account API."""

import json
import logging
import os
from datetime import datetime, timezone

from . import auth_store, client, entitlement_cache
import storage

log = logging.getLogger(__name__)


def sync_entitlements_from_server():
    if not auth_store.is_authenticated():
        return None
    try:
        payload = client.get_entitlements()
        entitlement_cache.update_from_entitlements(payload)
        return payload
    except client.AccountOfflineError:
        log.warning("Entitlement sync offline")
        cached = entitlement_cache.load_cache()
        return cached if cached else None
    except Exception:
        log.exception("Entitlement sync failed")
        cached = entitlement_cache.load_cache()
        return cached if cached else None


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
