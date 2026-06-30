"""Export invoice PDFs before uninstall (Windows; FrogsWork.exe --export-uninstall-data)."""

import os
import shutil
import sys
from datetime import date

import storage
from app_config import APP_BRAND_NAME


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


def export_for_uninstall():
    """Copy invoice PDFs to Downloads silently. Never blocks uninstall."""
    downloads = _downloads_dir()
    if not downloads or not os.path.isdir(downloads):
        return 0

    try:
        pdf_dir = storage.get_pdf_dir()
    except Exception:
        return 0

    pdfs = []
    if os.path.isdir(pdf_dir):
        pdfs = [name for name in os.listdir(pdf_dir) if name.lower().endswith(".pdf")]

    if not pdfs:
        return 0

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
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(export_for_uninstall())
