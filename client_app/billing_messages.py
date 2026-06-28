"""Customer-facing billing and account messages."""

OFFLINE_CONNECT = (
    "Could not reach account services. "
    "Check your internet connection and try again."
)
OFFLINE_SYNC = (
    "Could not sync your account. "
    "Check your internet connection and try again."
)

ACCOUNT_REQUIRED = (
    "This invoice would exceed the free $2,000/month allowance. "
    "Create an account to continue. Your invoice details are saved."
)

SESSION_EXPIRED = "Your session has expired. Sign in again."

INVALID_CREDENTIALS = "Email or password incorrect."

SIGNUP_OFFLINE = OFFLINE_CONNECT

GENERIC_BILLING_ERROR = "Something went wrong. Try again in a moment."

LEDGER_INVALID = (
    "Local usage records could not be verified. "
    "Go to Settings → Your account to rebuild from invoices or reset the usage cache."
)

LEDGER_REPAIRED = "Usage records rebuilt from your invoices for this month."
LEDGER_RESET = "Usage cache reset for this month."
LEDGER_REPAIR_FAILED = "Could not repair usage records. Try reset, or contact support."


def offline_for_preview(*, authenticated, account_required):
    if authenticated:
        return OFFLINE_SYNC
    if account_required:
        return OFFLINE_CONNECT
    return None


def offline_for_generate(*, authenticated):
    if authenticated:
        return OFFLINE_SYNC
    return OFFLINE_CONNECT


def map_http_auth_error(message):
    if message and "expired" in message.lower():
        return SESSION_EXPIRED
    if message and ("password" in message.lower() or "email" in message.lower()):
        return INVALID_CREDENTIALS
    if message and "internal server error" in message.lower():
        return (
            "Account services hit a server error. "
            "If this keeps happening, contact support — the billing database may need attention."
        )
    if message and "temporarily unavailable" in message.lower():
        return (
            "Account services are temporarily unavailable. "
            "Try again shortly, or contact support if the problem continues."
        )
    return message or GENERIC_BILLING_ERROR
