"""Account API client, auth, entitlements, and subscription messaging."""

from . import auth_store, client, entitlement_cache, entitlement_guard, install_secret, messages, sync, trial_stats
from .auth_store import clear_auth, get_server_url, is_authenticated, load_auth, save_auth, set_server_url
from .client import (
    AccountError,
    AccountOfflineError,
    SubscriptionRequiredError,
    attach_checkout_session,
    check_server_available,
    get_checkout_session_info,
    get_entitlements,
    login,
    logout,
    map_http_auth_error,
    register,
)
from .sync import start_background_sync, sync_entitlements_from_server

__all__ = [
    "AccountError",
    "AccountOfflineError",
    "SubscriptionRequiredError",
    "attach_checkout_session",
    "auth_store",
    "clear_auth",
    "client",
    "check_server_available",
    "entitlement_cache",
    "entitlement_guard",
    "get_checkout_session_info",
    "get_entitlements",
    "get_server_url",
    "install_secret",
    "is_authenticated",
    "load_auth",
    "login",
    "logout",
    "map_http_auth_error",
    "messages",
    "register",
    "save_auth",
    "set_server_url",
    "start_background_sync",
    "sync",
    "sync_entitlements_from_server",
    "trial_stats",
]
