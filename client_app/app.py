"""FrogsWork desktop entry: Cloud shell (pywebview) + uninstall/update hooks."""

import logging
import os
import sys
import threading

# Uninstall helper must exit before desktop imports (Inno: FrogsWork.exe --export-uninstall-data).
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--export-uninstall-data":
    from app_platform.win.uninstall import export_for_uninstall

    raise SystemExit(export_for_uninstall())

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _desktop_app_url():
    from app_config import DESKTOP_APP_URL

    override = (os.environ.get("FROGSWORK_DESKTOP_APP_URL") or "").strip()
    return override or DESKTOP_APP_URL


def _on_close():
    """Window closed: allow the process to exit cleanly."""
    log.info("Desktop shell closing")


def main():
    from desktop_shell import run_desktop_app

    def _telemetry_on_start():
        try:
            from account import telemetry

            telemetry.send_heartbeat()
        except Exception:
            log.debug("Telemetry heartbeat skipped", exc_info=True)

    threading.Thread(target=_telemetry_on_start, daemon=True, name="telemetry-heartbeat").start()

    url = _desktop_app_url()
    log.info("Opening Cloud app at %s", url)
    run_desktop_app(url, _on_close)


if __name__ == "__main__":
    main()
