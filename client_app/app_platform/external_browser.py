"""Open URLs in the system default browser (outside the pywebview shell)."""

import webbrowser


def open_external(url):
    """Open *url* in the user's default browser. Returns True if dispatch succeeded."""
    url = (url or "").strip()
    if not url:
        return False
    try:
        return webbrowser.open(url, new=1)
    except OSError:
        return False
