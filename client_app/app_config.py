"""Application constants and shipped defaults."""

import os

DEFAULT_ACCOUNT_API_URL = os.environ.get("FROGSWORK_ACCOUNT_API_URL") or "https://api.frogswork.com"
# Windows: %APPDATA%\<APP_DATA_DIR_NAME>\ — macOS/Linux use platformdirs later.
APP_DATA_DIR_NAME = "FrogsWork"

# Cloud UI hosted by the desktop shell (override with FROGSWORK_DESKTOP_APP_URL for Vite/staging).
DESKTOP_APP_URL = os.environ.get("FROGSWORK_DESKTOP_APP_URL") or "https://app.frogswork.com"
CLOUD_API_URL = os.environ.get("FROGSWORK_ACCOUNT_API_URL") or "https://api.frogswork.com"

# Legacy local Flask URL (no longer used by the shell; kept for any remaining scripts).
LOCAL_APP_HOST = "127.0.0.1"
LOCAL_APP_PORT = 5000
LOCAL_APP_URL = f"http://{LOCAL_APP_HOST}:{LOCAL_APP_PORT}/"

APP_VERSION = "3.1.2"

APP_BRAND_NAME = "FrogsWork"
APP_BRAND_TAGLINE = "Sales invoicing for Australian sole traders"
APP_BRAND_URL = "https://frogswork.com"


def _web_marketing_base():
    """Use local marketing server when the account API is local (dev)."""
    api_url = (os.environ.get("FROGSWORK_ACCOUNT_API_URL") or DEFAULT_ACCOUNT_API_URL or "").strip()
    if api_url.startswith(("http://127.0.0.1", "http://localhost")):
        return os.environ.get("FROGSWORK_WEB_MARKETING_URL", "http://127.0.0.1:8080").rstrip("/")
    return APP_BRAND_URL.rstrip("/")


_WEB_MARKETING = _web_marketing_base()
WEB_ACCOUNT_SIGNUP_URL = f"{_WEB_MARKETING}/account/signup.html"
WEB_ACCOUNT_SUBSCRIBE_URL = f"{_WEB_MARKETING}/account/subscribe.html"
WEB_ACCOUNT_UPGRADE_CLOUD_URL = f"{_WEB_MARKETING}/account/subscribe.html?upgrade=1&tier=cloud"
WEB_ACCOUNT_LOGIN_URL = f"{_WEB_MARKETING}/account/login.html?next=desktop"
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

# Subscribed users: offline grace before generate is blocked for verification.
SUBSCRIPTION_OFFLINE_GRACE_DAYS = 14
SUBSCRIPTION_OFFLINE_REMINDER_DAYS = 7

# Marketing display (Stripe handles actual billing).
SUBSCRIPTION_MONTHLY_DISPLAY = "$12.99/mo"
SUBSCRIPTION_ANNUAL_DISPLAY = "$129.90/yr"
SUBSCRIPTION_ANNUAL_SAVINGS = "2 months free"

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
APP_ICON_PATH = os.path.join(_ASSETS_DIR, "app.ico")
APP_SPLASH_LOGO_PATH = os.path.join(_ASSETS_DIR, "splash-logo.png")
