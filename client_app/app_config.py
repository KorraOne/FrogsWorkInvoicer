"""Application constants and shipped defaults."""

import os

DEFAULT_BILLING_SERVER_URL = os.environ.get("FROGSWORK_BILLING_URL") or "http://127.0.0.1:8080"

# Windows: %APPDATA%\<APP_DATA_DIR_NAME>\ — macOS/Linux use platformdirs later.
APP_DATA_DIR_NAME = "FrogsWork"

LOCAL_APP_HOST = "127.0.0.1"
LOCAL_APP_PORT = 5000
LOCAL_APP_URL = f"http://{LOCAL_APP_HOST}:{LOCAL_APP_PORT}/"

APP_VERSION = "1.0.2"

APP_BRAND_NAME = "FrogsWork"
APP_BRAND_TAGLINE = "Sales invoicing for Australian sole traders"
APP_BRAND_URL = "https://frogswork.com"
APP_BRAND_DEVELOPER = "KorraOne"
APP_BRAND_DEVELOPER_URL = "https://korraone.com"
APP_SUPPORT_URL = "https://korraone.com/support"
# Optional. If set, logo-design form offers a mailto link after submit.
APP_SUPPORT_EMAIL = os.environ.get("FROGSWORK_SUPPORT_EMAIL", "").strip()

APP_WINDOW_TITLE = APP_BRAND_NAME
APP_WINDOW_WIDTH = 1100
APP_WINDOW_HEIGHT = 800
APP_WINDOW_MIN_WIDTH = 900
APP_WINDOW_MIN_HEIGHT = 640

# Minimum time the splash stays visible (seconds), measured from first paint.
APP_SPLASH_MIN_SECONDS = 3.0

# Temporary Settings entry for logo design outreach. Remove in a later release.
SHOW_LOGO_DESIGN_SETTINGS = True

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
APP_ICON_PATH = os.path.join(_ASSETS_DIR, "app.ico")
APP_SPLASH_LOGO_PATH = os.path.join(_ASSETS_DIR, "splash-logo.png")
