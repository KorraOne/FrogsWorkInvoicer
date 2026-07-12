"""HTTP client for FrogsWork account API (auth, checkout, entitlements)."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from . import auth_store

log = logging.getLogger(__name__)


class AccountError(Exception):
    pass


class AccountOfflineError(AccountError):
    pass


class SubscriptionRequiredError(AccountError):
    pass


def _api_url(path):
    return auth_store.get_server_url().rstrip("/") + path


def _request(method, path, body=None, auth=False, timeout=15):
    headers = {"Accept": "application/json", "User-Agent": "FrogsWork/1.0"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if auth:
        auth_data = auth_store.load_auth()
        token = auth_data.get("access_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(_api_url(path), data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail)
            message = payload.get("error") or payload.get("message") or detail
        except json.JSONDecodeError:
            if exc.code == 404:
                message = "Account server endpoint not found. Restart account_api dev server (python server.py)."
            elif "<html" in detail.lower():
                message = f"Account server error ({exc.code}). Is the API running on port 8787?"
            else:
                message = detail.strip() or exc.reason
        raise AccountError(message) from exc
    except urllib.error.URLError as exc:
        raise AccountOfflineError(str(exc.reason)) from exc


def api_headers():
    return {"Accept": "application/json", "User-Agent": "FrogsWork/1.0"}


def check_server_available():
    try:
        _request("GET", "/health", timeout=5)
        return True
    except Exception:
        return False


def login(email, password):
    payload = _request("POST", "/auth/login", {"email": email, "password": password})
    auth_store.save_auth(
        {
            "email": email.strip().lower(),
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", ""),
            "server_url": auth_store.get_server_url(),
        }
    )
    return payload


def register(password, checkout_session_id, *, install_id=None, signup_snapshot=None):
    body = {
        "password": password,
        "checkout_session_id": checkout_session_id,
    }
    if install_id:
        body["install_id"] = install_id
    if signup_snapshot:
        body["signup_snapshot"] = signup_snapshot
    payload = _request("POST", "/auth/register", body)
    email = (payload.get("email") or "").strip().lower()
    auth_store.save_auth(
        {
            "email": email,
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", ""),
            "server_url": auth_store.get_server_url(),
        }
    )
    return payload


def get_checkout_session_info(session_id):
    query = urllib.parse.urlencode({"session_id": session_id})
    return _request("GET", f"/checkout/session-info?{query}")


def attach_checkout_session(checkout_session_id):
    return _request(
        "POST",
        "/auth/attach-checkout",
        {"checkout_session_id": checkout_session_id},
        auth=True,
    )


def logout():
    auth_store.clear_auth()
    from . import entitlement_cache

    entitlement_cache.clear_cache()


def _refresh_if_needed():
    auth = auth_store.load_auth()
    refresh = auth.get("refresh_token")
    if not refresh:
        return
    try:
        payload = _request("POST", "/auth/refresh", {"refresh_token": refresh})
        auth["access_token"] = payload["access_token"]
        if payload.get("refresh_token"):
            auth["refresh_token"] = payload["refresh_token"]
        auth_store.save_auth(auth)
    except AccountError:
        logout()
        raise


def resend_verification():
    return _request("POST", "/auth/resend-verification", auth=True)


def get_entitlements():
    try:
        return _request("GET", "/entitlements", auth=True)
    except AccountError as exc:
        if "401" in str(exc) or "token" in str(exc).lower():
            _refresh_if_needed()
            return _request("GET", "/entitlements", auth=True)
        raise


# Re-export document API helpers
from .documents import (  # noqa: E402
    documents_bootstrap,
    documents_download_pdf,
    documents_migrate,
    documents_sync,
    enqueue_invoice_send,
)


def map_http_auth_error(message):
    from . import messages

    return messages.map_http_auth_error(message)
