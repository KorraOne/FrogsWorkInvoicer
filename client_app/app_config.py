"""Application constants and shipped defaults."""

import os

DEFAULT_ACCOUNT_API_URL = os.environ.get("FROGSWORK_ACCOUNT_API_URL") or "http://127.0.0.1:8787"
# Windows: %APPDATA%\<APP_DATA_DIR_NAME>\ — macOS/Linux use platformdirs later.
APP_DATA_DIR_NAME = "FrogsWork"

LOCAL_APP_HOST = "127.0.0.1"
LOCAL_APP_PORT = 5000
LOCAL_APP_URL = f"http://{LOCAL_APP_HOST}:{LOCAL_APP_PORT}/"

# Configure Stripe Payment Link "After payment" redirect to this URL (literal braces for Stripe).
STRIPE_CHECKOUT_RETURN_URL = (
    f"http://{LOCAL_APP_HOST}:{LOCAL_APP_PORT}/account/stripe/return"
    "?session_id={CHECKOUT_SESSION_ID}"
)

APP_VERSION = "2.2.8"

APP_BRAND_NAME = "FrogsWork"
APP_BRAND_TAGLINE = "Sales invoicing for Australian sole traders"
APP_BRAND_URL = "https://frogswork.com"
APP_BRAND_DEVELOPER = "KorraOne"
APP_BRAND_DEVELOPER_URL = "https://korraone.com"
APP_SUPPORT_URL = "https://frogswork.com/support.html"
APP_PRIVACY_URL = "https://frogswork.com/privacy.html"
APP_TERMS_URL = "https://frogswork.com/terms.html"
# User-facing support and logo-design contact.
APP_SUPPORT_EMAIL = "crombie@korraone.com"
APP_LOGO_DESIGN_EMAIL = APP_SUPPORT_EMAIL

APP_WINDOW_TITLE = APP_BRAND_NAME
APP_WINDOW_WIDTH = 1100
APP_WINDOW_HEIGHT = 800
APP_WINDOW_MIN_WIDTH = 900
APP_WINDOW_MIN_HEIGHT = 640

# Minimum time the splash stays visible (seconds), measured from first paint.
APP_SPLASH_MIN_SECONDS = 3.0

# Temporary Settings entry for logo design outreach. Remove in a later release.
SHOW_LOGO_DESIGN_SETTINGS = True

# Free trial before account + subscription required (lifetime totals).
TRIAL_MAX_INVOICES = 20
TRIAL_MAX_EX_GST = 20_000

# Subscribed users: offline grace before generate is blocked for verification.
SUBSCRIPTION_OFFLINE_GRACE_DAYS = 14
SUBSCRIPTION_OFFLINE_REMINDER_DAYS = 7

# Marketing display (Stripe handles actual billing).
SUBSCRIPTION_MONTHLY_DISPLAY = "$12.99/mo"
SUBSCRIPTION_ANNUAL_DISPLAY = "$129.90/yr"
SUBSCRIPTION_ANNUAL_SAVINGS = "2 months free"

# Stripe Payment Links (Dashboard → Payment links). No API call needed for checkout.
STRIPE_PAYMENT_LINK_MONTHLY = os.environ.get("STRIPE_PAYMENT_LINK_MONTHLY", "").strip()
STRIPE_PAYMENT_LINK_ANNUAL = os.environ.get("STRIPE_PAYMENT_LINK_ANNUAL", "").strip()

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
APP_ICON_PATH = os.path.join(_ASSETS_DIR, "app.ico")
APP_SPLASH_LOGO_PATH = os.path.join(_ASSETS_DIR, "splash-logo.png")
