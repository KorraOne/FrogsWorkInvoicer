"""User-facing copy for trial and subscription gating."""

TRIAL_GATE = (
    "You have reached the free trial limit (20 invoices or $20,000 ex GST lifetime). "
    "Create an account and subscribe to keep generating invoices."
)

SUBSCRIBE_REQUIRED = (
    "Subscribe to FrogsWork to generate more invoices. Your invoice data stays on this computer."
)

SYNC_REQUIRED = (
    "It has been {days} days since we last verified your subscription. "
    "Connect to the internet and verify so we can confirm you are still subscribed."
)

SYNC_REMINDER = "Connect when you can so we can verify your subscription."

OFFLINE_CONNECT = "Could not reach FrogsWork servers. Check your internet connection and try again."

OFFLINE_VERIFY = "You are offline. Connect to verify your subscription."

GENERIC_ACCOUNT_ERROR = "Something went wrong with your account. Try again or contact support."

SIGNUP_OFFLINE = "Sign-up needs an internet connection to link your subscription."

SUBSCRIPTION_INACTIVE = (
    "Your subscription is not active. Manage billing in your account settings to resubscribe."
)


def map_http_auth_error(message):
    text = (message or "").strip()
    if not text:
        return GENERIC_ACCOUNT_ERROR
    lower = text.lower()
    if "invalid" in lower and ("password" in lower or "credentials" in lower):
        return "Email or password is incorrect."
    if "already" in lower and "registered" in lower:
        return "An account with this email already exists. Try signing in."
    if "subscription" in lower:
        return SUBSCRIPTION_INACTIVE
    return text
