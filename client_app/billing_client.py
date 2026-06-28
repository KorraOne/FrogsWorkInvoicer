"""HTTP client for the KorraOne billing server."""

import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal

import billing_auth_store
import billing_core
import billing_ledger
import billing_local
import billing_messages

log = logging.getLogger(__name__)


def api_headers(extra=None):
    """Headers for billing API calls (Cloudflare blocks default Python urllib)."""
    from app_config import APP_BRAND_NAME, APP_VERSION

    headers = {
        "User-Agent": f"{APP_BRAND_NAME}/{APP_VERSION} (Windows; Desktop)",
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


class BillingError(Exception):
    pass


class BillingOfflineError(BillingError):
    pass


class AccountRequiredError(BillingError):
    pass


class CapBlockedError(BillingError):
    def __init__(self, message, preview=None):
        super().__init__(message)
        self.preview = preview or {}


def _request(method, path, body=None, auth=True, _retried=False):
    url = billing_auth_store.get_server_url() + path
    headers = api_headers({"Content-Type": "application/json"})
    if auth:
        tokens = billing_auth_store.load_auth()
        if tokens.get("access_token"):
            headers["Authorization"] = f"Bearer {tokens['access_token']}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 204:
                return {}
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc)
            msg = detail.get("error", exc.reason)
        except Exception:
            detail = {}
            msg = exc.reason
        log.warning("Billing API %s %s -> HTTP %s: %s", method, path, exc.code, msg)
        if exc.code == 401 and auth and not _retried:
            auth_data = billing_auth_store.load_auth()
            refresh_token = auth_data.get("refresh_token")
            if refresh_token:
                try:
                    result = _request(
                        "POST",
                        "/auth/refresh",
                        {"refresh_token": refresh_token},
                        auth=False,
                    )
                    _store_tokens(result)
                    return _request(method, path, body, auth, _retried=True)
                except BillingError:
                    pass
            billing_auth_store.clear_auth()
            raise BillingError(billing_messages.SESSION_EXPIRED)
        if exc.code == 401 and auth:
            billing_auth_store.clear_auth()
            raise BillingError(billing_messages.SESSION_EXPIRED)
        if exc.code == 403 and "account" in str(msg).lower():
            raise AccountRequiredError(msg)
        if exc.code == 403:
            raise BillingOfflineError(billing_messages.OFFLINE_CONNECT)
        if exc.code == 409:
            preview = detail.get("preview") if isinstance(detail, dict) else {}
            raise CapBlockedError(msg, preview)
        raise BillingError(msg)
    except urllib.error.URLError as exc:
        log.warning("Billing API %s %s unreachable: %s", method, path, exc.reason)
        raise BillingOfflineError(billing_messages.OFFLINE_CONNECT) from exc


def _local_usage_fallback(session_expired=False):
    snap = billing_local.local_usage_snapshot()
    snap["server_required"] = False
    if session_expired:
        snap["session_expired"] = True
    return snap


def check_server_available():
    url = billing_auth_store.get_server_url() + "/health"
    req = urllib.request.Request(url, headers=api_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def register(email, password, cap_enabled, cap_amount_ex_gst, billing_cycle="quarterly"):
    try:
        initial_usage = billing_local.export_events_for_signup()
    except billing_ledger.BillingIntegrityError as exc:
        raise BillingError(billing_messages.LEDGER_INVALID) from exc
    body = {
        "email": email,
        "password": password,
        "cap_enabled": cap_enabled,
        "cap_amount_ex_gst": str(cap_amount_ex_gst) if cap_amount_ex_gst else None,
        "billing_cycle": billing_cycle,
        "initial_usage": initial_usage,
    }
    result = _request("POST", "/auth/register", body, auth=False)
    _store_tokens(result)
    return result


def login(email, password):
    result = _request("POST", "/auth/login", {"email": email, "password": password}, auth=False)
    _store_tokens(result)
    return result


def logout():
    billing_auth_store.clear_auth()


def _store_tokens(result):
    if not result.get("access_token"):
        raise BillingError(billing_messages.GENERIC_BILLING_ERROR)
    auth = billing_auth_store.load_auth()
    auth.update(
        {
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token"),
            "email": result.get("email"),
            "server_url": billing_auth_store.get_server_url(),
        }
    )
    try:
        billing_auth_store.save_auth(auth)
    except Exception as exc:
        raise BillingError(billing_messages.GENERIC_BILLING_ERROR) from exc


def refresh_if_needed():
    auth = billing_auth_store.load_auth()
    if not auth.get("refresh_token"):
        return
    try:
        result = _request(
            "POST",
            "/auth/refresh",
            {"refresh_token": auth["refresh_token"]},
            auth=False,
        )
        _store_tokens(result)
    except BillingError:
        pass


def get_usage():
    if not billing_auth_store.is_authenticated():
        return _local_usage_fallback()
    refresh_if_needed()
    try:
        data = _request("GET", "/usage")
    except BillingError:
        return _local_usage_fallback(session_expired=True)
    except BillingOfflineError:
        snap = billing_local.local_usage_snapshot()
        snap["server_required"] = True
        return snap
    return _normalize_preview(data)


def preview(amount_ex_gst):
    amount = Decimal(str(amount_ex_gst))
    if not billing_auth_store.is_authenticated():
        return billing_local.local_usage_snapshot(amount)
    refresh_if_needed()
    data = _request("POST", "/usage/preview", {"amount_ex_gst": str(amount)})
    return _normalize_preview(data)


def commit(invoice_number, amount_ex_gst, cap_bypassed=False):
    amount = Decimal(str(amount_ex_gst))
    if not billing_auth_store.is_authenticated():
        snap = billing_local.local_usage_snapshot(amount)
        if snap.get("ledger_invalid"):
            raise BillingError(billing_messages.LEDGER_INVALID)
        if snap.get("account_required"):
            raise AccountRequiredError(billing_messages.ACCOUNT_REQUIRED)
        if snap.get("cap_blocked") and not cap_bypassed:
            raise CapBlockedError("Cap exceeded", snap)
        billing_local.record_local_commit(invoice_number, amount)
        return {"ok": True, "local": True}
    refresh_if_needed()
    return _request(
        "POST",
        "/usage/commit",
        {
            "invoice_number": int(invoice_number),
            "amount_ex_gst": str(amount),
            "usage_month": billing_core.current_usage_month(),
            "cap_bypassed": cap_bypassed,
        },
    )


def update_cap(cap_enabled, cap_amount_ex_gst, scope="permanent"):
    refresh_if_needed()
    return _request(
        "PATCH",
        "/account/cap",
        {
            "cap_enabled": cap_enabled,
            "cap_amount_ex_gst": str(cap_amount_ex_gst) if cap_amount_ex_gst else None,
            "scope": scope,
        },
    )


def get_billing_overview():
    refresh_if_needed()
    return _request("GET", "/account/billing")


def update_billing_cycle(billing_cycle):
    refresh_if_needed()
    return _request("PATCH", "/account/billing-cycle", {"billing_cycle": billing_cycle})


def server_required_for(amount_ex_gst):
    preview_data = preview(amount_ex_gst)
    return preview_data.get("server_required") or preview_data.get("account_required")


def _normalize_preview(data):
    total = Decimal(str(data.get("month_total_ex_gst", data.get("projected_x", 0))))
    fee = Decimal(str(data.get("projected_fee", data.get("fee_so_far", 0))))
    fee_now = Decimal(str(data.get("fee_so_far", 0)))
    cap_amount = data.get("cap_amount_ex_gst")
    return {
        "usage_month": data.get("usage_month", billing_core.current_usage_month()),
        "month_total_ex_gst": total,
        "fee_so_far": fee_now,
        "projected_fee": fee,
        "fee_delta": Decimal(str(data.get("fee_delta", fee - fee_now))),
        "free_remaining": Decimal(str(data.get("free_remaining", billing_core.free_remaining(total)))),
        "cap_enabled": data.get("cap_enabled", False),
        "cap_amount_ex_gst": Decimal(cap_amount) if cap_amount not in (None, "") else None,
        "cap_blocked": data.get("cap_blocked", False),
        "over_by": Decimal(str(data.get("over_by", 0))),
        "account_required": data.get("account_required", False),
        "account_authenticated": billing_auth_store.is_authenticated(),
        "server_required": True,
    }
