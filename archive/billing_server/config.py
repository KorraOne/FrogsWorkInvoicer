import os

from dotenv import load_dotenv

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_SERVER_DIR, ".env"))
_DEFAULT_DATABASE = os.path.join(_SERVER_DIR, "billing.db")
_DEFAULT_PLATFORM_INVOICE_DIR = os.path.join(_SERVER_DIR, "platform_invoices")

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me-in-production-32chars")
JWT_ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_MINUTES", "30"))
JWT_REFRESH_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "30"))
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_DATABASE)
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080")

FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-flask-secret-change-me-in-production")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_SESSION_HOURS = int(os.environ.get("ADMIN_SESSION_HOURS", "8"))
PLATFORM_INVOICE_DIR = os.environ.get("PLATFORM_INVOICE_DIR", _DEFAULT_PLATFORM_INVOICE_DIR)

KORRAONE_BUSINESS = {
    "name": os.environ.get("KORRAONE_NAME", "KorraOne"),
    "abn": os.environ.get("KORRAONE_ABN", ""),
    "address": os.environ.get("KORRAONE_ADDRESS", ""),
    "bsb": os.environ.get("KORRAONE_BSB", ""),
    "acc": os.environ.get("KORRAONE_ACC", ""),
    "payid": os.environ.get("KORRAONE_PAYID", ""),
    "payment_terms": os.environ.get("KORRAONE_PAYMENT_TERMS", "14 days"),
}

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "billing@korraone.com")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") not in ("0", "false", "False")
BILLING_EMAIL_ENABLED = bool(SMTP_HOST)

# Desktop client update (GET /releases/latest). Leave version empty to disable.
CLIENT_RELEASE_VERSION = os.environ.get("CLIENT_RELEASE_VERSION", "").strip()
CLIENT_RELEASE_URL = os.environ.get("CLIENT_RELEASE_URL", "").strip()
CLIENT_RELEASE_SHA256 = os.environ.get("CLIENT_RELEASE_SHA256", "").strip().lower()
CLIENT_RELEASE_NOTES = os.environ.get("CLIENT_RELEASE_NOTES", "").strip()
