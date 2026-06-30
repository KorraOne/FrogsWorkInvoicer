from . import auth_store, entitlement_cache, messages, trial_stats
from app_config import SUBSCRIPTION_OFFLINE_GRACE_DAYS


def _sync_block_message():
    days = entitlement_cache.days_since_verified()
    if days is None:
        days = SUBSCRIPTION_OFFLINE_GRACE_DAYS + 1
    return messages.SYNC_REQUIRED.format(days=days)


def check_generate_access():
    """
    Return (allowed, status, message).
    status: None | trial_ok | subscribe_required | account_required | sync_required | subscription_inactive
    """
    if trial_stats.under_trial_limits():
        return True, "trial_ok", None

    if not auth_store.is_authenticated():
        return False, "account_required", messages.TRIAL_GATE

    if entitlement_cache.subscription_active_with_grace():
        sync_state = entitlement_cache.sync_status()
        if sync_state == "grace_expired":
            return False, "sync_required", _sync_block_message()
        return True, "subscribed", None

    cache = entitlement_cache.load_cache()
    if cache.get("active") is False and cache.get("last_verified_at"):
        return False, "subscription_inactive", messages.SUBSCRIPTION_INACTIVE

    if entitlement_cache.sync_status() in ("grace_expired", "never_verified"):
        return False, "sync_required", _sync_block_message()

    return False, "subscribe_required", messages.SUBSCRIBE_REQUIRED


def preview_context(format_money):
    """Template context for preview page gating banners."""
    allowed, status, message = check_generate_access()
    sync_state = entitlement_cache.sync_status()
    reminder = None
    if auth_store.is_authenticated() and sync_state == "reminder":
        reminder = messages.SYNC_REMINDER
    meter = trial_stats.meter_snapshot()
    meter["lifetime_ex_gst_fmt"] = format_money(meter["lifetime_ex_gst_total"])
    meter["max_ex_gst_fmt"] = format_money(meter["max_ex_gst"])
    meter["amount_remaining_fmt"] = format_money(meter["amount_remaining_ex_gst"])
    return {
        "generate_allowed": allowed,
        "gate_status": status,
        "gate_message": message,
        "sync_reminder": reminder,
        "trial_meter": meter,
    }
