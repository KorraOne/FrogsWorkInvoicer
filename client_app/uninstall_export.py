"""Export invoice PDFs before uninstall (called via FrogsWork.exe --export-uninstall-data)."""

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


def _message_box(text, title=None, error=False):
    if os.name != "nt":
        print(text)
        return
    import ctypes

    flags = 0x00000010 if error else 0x00000040
    ctypes.windll.user32.MessageBoxW(0, text, title or APP_BRAND_NAME, 0x00000000 | flags)


def export_for_uninstall():
    downloads = _downloads_dir()
    if not downloads or not os.path.isdir(downloads):
        _message_box(
            "Could not find your Downloads folder.\n\nUninstall will continue without exporting PDFs.",
            error=True,
        )
        return 1

    try:
        pdf_dir = storage.get_pdf_dir()
    except Exception as exc:
        _message_box(f"Could not read PDF folder settings:\n{exc}", error=True)
        return 1

    stamp = date.today().isoformat()
    export_root = os.path.join(downloads, f"FrogsWork-Uninstall-{stamp}")
    export_pdfs = os.path.join(export_root, "pdfs")

    pdfs = []
    if os.path.isdir(pdf_dir):
        pdfs = [name for name in os.listdir(pdf_dir) if name.lower().endswith(".pdf")]

    if not pdfs:
        _message_box(
            "No invoice PDFs were found to export.\n\nYour FrogsWork data will be removed from this PC.",
        )
        return 0

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
    except OSError as exc:
        _message_box(f"Could not export PDFs to Downloads:\n{exc}", error=True)
        return 1

    _message_box(
        f"Exported {copied} invoice PDF(s) to:\n\n{export_root}\n\n"
        "Your other FrogsWork data on this PC will now be removed.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(export_for_uninstall())
