"""Cloud account export before uninstall (Windows; FrogsWork.exe --export-uninstall-data)."""

import json
import os
import shutil
import sys
from datetime import date

from app_config import APP_BRAND_NAME, APP_DATA_DIR_NAME, CLOUD_API_URL

PDF_MARKER_FILENAME = ".frogswork-pdfs"


def _appdata_dir():
    base = os.environ.get("APPDATA", "").strip()
    if not base:
        return ""
    return os.path.join(base, APP_DATA_DIR_NAME)


def _read_bootstrap_pdf_folder():
    appdata = _appdata_dir()
    if not appdata:
        return ""
    path = os.path.join(appdata, "bootstrap.json")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    return (data.get("pdf_folder") or "").strip()


def _downloads_dir():
    userprofile = os.environ.get("USERPROFILE", "").strip()
    if not userprofile:
        return ""
    onedrive = os.environ.get("OneDrive", "").strip()
    if onedrive:
        candidate = os.path.join(onedrive, "Downloads")
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(userprofile, "Downloads")


def _remove_marked_pdf_folder(pdf_dir):
    """Remove installer/app PDF folder when it carries our marker file."""
    if not pdf_dir:
        return
    pdf_dir = os.path.abspath(pdf_dir)
    marker = os.path.join(pdf_dir, PDF_MARKER_FILENAME)
    if not os.path.isfile(marker):
        return
    try:
        shutil.rmtree(pdf_dir)
    except OSError:
        pass


def _write_readme(path, body):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError:
        pass


def _download_cloud_export(downloads):
    """
    Call the same GET /account/export used by Settings → Download my data.
    Requires session tokens persisted to AppData by the desktop Cloud shell.
    Returns True if a ZIP was written.
    """
    try:
        from account import auth_store, client
    except Exception:
        return False

    if not auth_store.is_authenticated():
        return False

    stamp = date.today().isoformat()
    dest = os.path.join(downloads, f"frogswork-export-{stamp}.zip")
    try:
        try:
            zip_bytes = client.download_account_export(timeout=120)
        except client.AccountError:
            # Access token may be stale; refresh once then retry.
            try:
                client._refresh_if_needed()
            except Exception:
                return False
            zip_bytes = client.download_account_export(timeout=120)
        if not zip_bytes:
            return False
        with open(dest, "wb") as f:
            f.write(zip_bytes)
        _write_readme(
            os.path.join(downloads, f"frogswork-export-{stamp}-README.txt"),
            (
                f"{APP_BRAND_NAME} was uninstalled from this PC.\n\n"
                f"Your Cloud data export was saved to:\n  {dest}\n\n"
                "This is the same ZIP as Settings → Download my data "
                "(invoices and quotes by status, plus account/business/customer JSON).\n"
                "It cannot be re-imported into FrogsWork.\n"
            ),
        )
        return True
    except Exception:
        return False


def export_for_uninstall():
    """Download Cloud export ZIP to Downloads when signed in. Never blocks uninstall."""
    pdf_dir = _read_bootstrap_pdf_folder()
    if not pdf_dir:
        appdata = _appdata_dir()
        if appdata:
            pdf_dir = os.path.join(appdata, "pdfs")

    try:
        from account import telemetry

        telemetry.send_uninstall_event()
    except Exception:
        pass

    downloads = _downloads_dir()
    if downloads and os.path.isdir(downloads):
        wrote = _download_cloud_export(downloads)
        if not wrote:
            # Not signed in on this PC (or export failed). Point the user at Cloud Settings.
            stamp = date.today().isoformat()
            api = (os.environ.get("FROGSWORK_ACCOUNT_API_URL") or CLOUD_API_URL or "").rstrip("/")
            _write_readme(
                os.path.join(downloads, f"FrogsWork-Uninstall-{stamp}-README.txt"),
                (
                    f"{APP_BRAND_NAME} was uninstalled from this PC.\n\n"
                    "No Cloud data export was saved automatically "
                    "(this Windows app was not signed in, or the export could not be downloaded).\n\n"
                    "Your invoices and quotes stay in FrogsWork Cloud until you delete them.\n"
                    "To download a copy: open https://app.frogswork.com → Settings → Download my data.\n"
                    f"(API: {api or 'https://api.frogswork.com'})\n"
                ),
            )

    _remove_marked_pdf_folder(pdf_dir)
    return 0


if __name__ == "__main__":
    sys.exit(export_for_uninstall())
