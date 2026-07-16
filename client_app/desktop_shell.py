"""Native desktop window shell (pywebview + Edge WebView2) hosting the Cloud app."""

import base64
import html
import logging
import mimetypes
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import app_config
import app_platform.window_state as window_state
from app_platform.external_browser import open_external

log = logging.getLogger(__name__)

_main_window = None
_desktop_mode = False
_is_maximized = False
_pending_geometry = None
_splash_shown_at = None

_SPLASH_STYLES = """
        {theme_css}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-family: "Segoe UI", system-ui, sans-serif;
            background: radial-gradient(120% 100% at 50% 0%, var(--fw-bg-top) 0%, var(--fw-bg-mid) 45%, var(--fw-bg-bottom) 100%);
            color: var(--fw-green-900);
        }}
        .splash {{
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 2rem;
            width: 100%;
        }}
        .splash-logo-wrap {{
            width: 7rem;
            height: 7rem;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .splash-logo {{
            width: 7rem;
            height: 7rem;
            object-fit: contain;
        }}
        .splash-logo-placeholder {{
            width: 7rem;
            height: 7rem;
            border-radius: 1.25rem;
            background: linear-gradient(145deg, var(--fw-surface) 0%, var(--fw-bg-top) 100%);
            border: 2px solid var(--fw-border);
            box-shadow: 0 12px 32px var(--fw-shadow);
        }}
        .splash-brand {{
            margin: 0;
            font-size: 2.5rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }}
        .splash-tagline {{
            margin: 0.75rem 0 2rem 0;
            font-size: 1.05rem;
            color: var(--fw-green-800);
            opacity: 0.85;
        }}
        .splash-progress {{
            width: min(14rem, 70vw);
            height: 0.25rem;
            border-radius: 999px;
            background: var(--fw-border);
            overflow: hidden;
        }}
        .splash-progress-bar {{
            width: 40%;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, var(--fw-green-600), var(--fw-green-500));
            animation: splash-progress 1.4s ease-in-out infinite;
        }}
        @keyframes splash-progress {{
            0% {{ transform: translateX(-120%); }}
            100% {{ transform: translateX(320%); }}
        }}
        .splash-footer {{
            padding: 1.25rem 1rem 1.75rem 1rem;
            font-size: 0.9rem;
            color: var(--fw-green-700);
            opacity: 0.9;
        }}
        .splash-footer a {{
            color: inherit;
            text-decoration: none;
            font-weight: 600;
        }}
        .splash-footer a:hover {{
            text-decoration: underline;
        }}
        .splash-error {{
            max-width: 26rem;
            margin-top: 1rem;
            padding: 0.85rem 1rem;
            border-radius: 0.75rem;
            background: rgba(255, 255, 255, 0.75);
            color: var(--fw-error);
            font-size: 0.95rem;
            line-height: 1.45;
        }}
"""

_SPLASH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{brand_name}</title>
    <style>
{splash_styles}
    </style>
</head>
<body>
    <div class="splash">
        <div class="splash-logo-wrap">{logo_markup}</div>
        <h1 class="splash-brand">{brand_name}</h1>
        <p class="splash-tagline">{tagline}</p>
        <div class="splash-progress" aria-hidden="true"><div class="splash-progress-bar"></div></div>
        {error_block}
    </div>
    <footer class="splash-footer">
        <a href="{brand_url}">{brand_name}</a>
        · <a href="{developer_url}">{developer}</a>
        · <a href="{support_url}">Support</a>
    </footer>
</body>
</html>"""


class DesktopBridge:
    """Exposed to the Cloud UI as window.pywebview.api."""

    def open_external(self, url):
        return bool(open_external(url))

    def get_api_base(self):
        override = (os.environ.get("FROGSWORK_ACCOUNT_API_URL") or "").strip()
        if override:
            return override.rstrip("/")
        return app_config.CLOUD_API_URL.rstrip("/")


def is_desktop_mode():
    return _desktop_mode


def get_main_window():
    return _main_window


def _resource_path(relative):
    base = getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def _splash_theme_css():
    path = _resource_path(os.path.join("static", "theme.css"))
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def _splash_logo_markup():
    logo_path = _resource_path(os.path.join("assets", "splash-logo.png"))
    if not os.path.isfile(logo_path):
        logo_path = app_config.APP_SPLASH_LOGO_PATH
    if os.path.isfile(logo_path):
        mime, _ = mimetypes.guess_type(logo_path)
        if not mime:
            mime = "image/png"
        with open(logo_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return (
            f'<img class="splash-logo" src="data:{mime};base64,{encoded}" '
            f'alt="{html.escape(app_config.APP_BRAND_NAME)} logo">'
        )
    return '<div class="splash-logo-placeholder" aria-hidden="true"></div>'


def _splash_html(tagline="Starting up…", error_message=None):
    error_block = ""
    if error_message:
        error_block = f'<p class="splash-error">{html.escape(error_message)}</p>'
    splash_styles = _SPLASH_STYLES.format(theme_css=_splash_theme_css())
    return _SPLASH_HTML.format(
        splash_styles=splash_styles,
        brand_name=html.escape(app_config.APP_BRAND_NAME),
        brand_url=html.escape(app_config.APP_BRAND_URL, quote=True),
        developer=html.escape(app_config.APP_BRAND_DEVELOPER),
        developer_url=html.escape(app_config.APP_BRAND_DEVELOPER_URL, quote=True),
        support_url=html.escape(app_config.APP_SUPPORT_URL, quote=True),
        logo_markup=_splash_logo_markup(),
        tagline=html.escape(tagline),
        error_block=error_block,
    )


def _wait_for_splash_paint(timeout=10.0):
    """Block until WebView reports first paint, or timeout."""
    deadline = time.perf_counter() + timeout
    while _splash_shown_at is None and time.perf_counter() < deadline:
        time.sleep(0.05)


def _ensure_min_splash_duration():
    _wait_for_splash_paint()
    if _splash_shown_at is None:
        time.sleep(app_config.APP_SPLASH_MIN_SECONDS)
        return
    remaining = app_config.APP_SPLASH_MIN_SECONDS - (time.perf_counter() - _splash_shown_at)
    if remaining > 0:
        time.sleep(remaining)


def _probe_url(url, timeout=2.0):
    """Best-effort reachability check (Cloud Pages or local Vite)."""
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": f"FrogsWork/{app_config.APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return False


def _initial_window_options(state):
    """Size/position for create_window — cheap JSON read, no startup delay."""
    options = {
        "width": app_config.APP_WINDOW_WIDTH,
        "height": app_config.APP_WINDOW_HEIGHT,
        "x": None,
        "y": None,
        "maximized": False,
    }
    if state.get("maximized"):
        options["maximized"] = True
    elif state.get("width") and state.get("height"):
        options["width"] = int(state["width"])
        options["height"] = int(state["height"])
        x = state.get("x")
        y = state.get("y")
        if x is not None and y is not None:
            options["x"] = int(x)
            options["y"] = int(y)
    else:
        options["maximized"] = True
    return options


def _capture_geometry(window):
    return {
        "maximized": _is_maximized,
        "width": window.width,
        "height": window.height,
        "x": window.x,
        "y": window.y,
    }


def _inject_host_bridge(window):
    """Ensure window.frogsworkDesktop exists for the Cloud UI host contract."""
    api_base = DesktopBridge().get_api_base().replace("\\", "\\\\").replace("'", "\\'")
    script = f"""
(function () {{
  function wire() {{
    var api = window.pywebview && window.pywebview.api;
    window.frogsworkDesktop = {{
      apiBase: '{api_base}',
      openExternal: function (url) {{
        if (api && api.open_external) {{
          return api.open_external(url);
        }}
        window.open(url, '_blank');
        return true;
      }}
    }};
    document.documentElement.classList.add('host-desktop');
    if (document.body) document.body.classList.add('host-desktop');
  }}
  if (window.pywebview && window.pywebview.api) {{
    wire();
  }} else {{
    window.addEventListener('pywebviewready', wire);
    wire();
  }}
}})();
"""
    try:
        window.evaluate_js(script)
    except Exception:
        log.debug("Host bridge inject failed", exc_info=True)


def run_desktop_app(app_url, on_close, startup_error=None):
    global _main_window, _desktop_mode, _is_maximized, _pending_geometry, _splash_shown_at

    import webview

    _desktop_mode = True
    saved = window_state.load_window_state()
    _pending_geometry = saved
    window_opts = _initial_window_options(saved)
    _is_maximized = window_opts["maximized"]
    startup_error = startup_error if startup_error is not None else {}
    bridge = DesktopBridge()

    def _handle_closing():
        if _main_window is not None:
            window_state.save_window_state(_capture_geometry(_main_window))
        on_close()

    def _on_shown():
        global _splash_shown_at
        _splash_shown_at = time.perf_counter()

    def _on_maximized():
        global _is_maximized
        _is_maximized = True

    def _on_restored():
        global _is_maximized
        _is_maximized = False

    def _on_loaded():
        if _main_window is not None:
            _inject_host_bridge(_main_window)

    def _navigate_when_ready():
        home_url = app_url.rstrip("/") + "/"
        deadline = time.perf_counter() + 20
        reachable = False

        while time.perf_counter() < deadline:
            if _probe_url(home_url) or _probe_url(app_url):
                reachable = True
                break
            time.sleep(0.2)

        _ensure_min_splash_duration()

        if _main_window is None:
            return

        if not reachable:
            # Still try to load; WebView may succeed when our probe did not (CORS/HEAD quirks).
            log.warning("Cloud app probe failed; loading %s anyway", app_url)

        _main_window.load_url(app_url)

    window_opts = _initial_window_options(saved)
    create_kwargs = {
        "title": app_config.APP_WINDOW_TITLE,
        "html": _splash_html(),
        "width": window_opts["width"],
        "height": window_opts["height"],
        "min_size": (app_config.APP_WINDOW_MIN_WIDTH, app_config.APP_WINDOW_MIN_HEIGHT),
        "easy_drag": False,
        "text_select": True,
        "maximized": window_opts["maximized"],
        "js_api": bridge,
    }
    if window_opts["x"] is not None and window_opts["y"] is not None:
        create_kwargs["x"] = window_opts["x"]
        create_kwargs["y"] = window_opts["y"]

    window = webview.create_window(**create_kwargs)
    _main_window = window
    window.events.closing += _handle_closing
    window.events.shown += _on_shown
    window.events.maximized += _on_maximized
    window.events.restored += _on_restored
    window.events.loaded += _on_loaded

    threading.Thread(target=_navigate_when_ready, daemon=True, name="splash-navigate").start()

    gui = "edgechromium" if sys.platform == "win32" else None
    webview.start(gui=gui)
