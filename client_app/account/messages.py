"""User-facing copy for account and subscription gating."""

ACCOUNT_REQUIRED = (
    "Sign in with an active subscription to create invoices."
)

SUBSCRIBE_REQUIRED = (
    "Subscribe to keep creating invoices. Your data stays on this computer."
)

SYNC_REQUIRED = (
    "Subscription not verified in {days} days. "
    "Go online and tap Verify subscription."
)

SYNC_REMINDER = "Go online when you can. Tap Verify subscription."

OFFLINE_CONNECT = "Could not reach FrogsWork. Check your internet and try again."

OFFLINE_VERIFY = "You're offline. Connect to verify your subscription."

GENERIC_ACCOUNT_ERROR = "Something went wrong. Try again or contact support."

SIGNUP_OFFLINE = "Sign-up needs internet to link your subscription."

SUBSCRIPTION_INACTIVE = (
    "Subscription not active. Open Your account to manage billing or resubscribe."
)


def map_http_auth_error(message):
    text = (message or "").strip()
    if not text:
        return GENERIC_ACCOUNT_ERROR
    lower = text.lower()
    if "invalid" in lower and ("password" in lower or "credentials" in lower):
        return "Wrong email or password."
    if "already" in lower and "registered" in lower:
        return "That email already has an account. Sign in."
    if "subscription" in lower:
        return SUBSCRIPTION_INACTIVE
    return text
