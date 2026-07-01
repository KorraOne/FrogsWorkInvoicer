"""Export invoice PDFs before uninstall (Windows; FrogsWork.exe --export-uninstall-data)."""

import json
import os
import shutil
import sys
from datetime import date

from app_config import APP_BRAND_NAME, APP_DATA_DIR_NAME

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


def export_for_uninstall():
    """Copy invoice PDFs to Downloads, then remove marked PDF folder. Never blocks uninstall."""
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
    if downloads and os.path.isdir(downloads) and pdf_dir and os.path.isdir(pdf_dir):
        pdfs = [name for name in os.listdir(pdf_dir) if name.lower().endswith(".pdf")]
        if pdfs:
            stamp = date.today().isoformat()
            export_root = os.path.join(downloads, f"FrogsWork-Uninstall-{stamp}")
            export_pdfs = os.path.join(export_root, "pdfs")
            try:
                os.makedirs(export_pdfs, exist_ok=True)
                copied = 0
                for name in pdfs:
                    src = os.path.join(pdf_dir, name)
                    if not os.path.isfile(src):
                        continue
                    shutil.copy2(src, os.path.join(export_pdfs, name))
                    copied += 1
                readme = os.path.join(export_root, "README.txt")
                with open(readme, "w", encoding="utf-8") as f:
                    f.write(
                        f"{APP_BRAND_NAME} was uninstalled from this PC.\n\n"
                        f"{copied} invoice PDF(s) were copied from:\n  {pdf_dir}\n\n"
                        f"to:\n  {export_pdfs}\n"
                    )
            except OSError:
                pass

    _remove_marked_pdf_folder(pdf_dir)
    return 0


if __name__ == "__main__":
    sys.exit(export_for_uninstall())
