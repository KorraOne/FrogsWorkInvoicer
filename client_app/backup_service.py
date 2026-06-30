"""Backup ZIP export — save dialog in desktop mode, browser download otherwise."""

import io
import os
import sys
import zipfile
from datetime import datetime

import storage


class BackupExportError(Exception):
    pass


def build_backup_zip(exe_dir):
    """Return (zip_bytes_io, timestamp_stamp)."""
    buf = io.BytesIO()
    data_path = storage.get_data_path()
    pdf_dir = storage.get_pdf_dir()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in os.listdir(data_path):
            path = os.path.join(data_path, name)
            if os.path.isfile(path):
                zf.write(path, name)
        if os.path.isdir(pdf_dir):
            for name in os.listdir(pdf_dir):
                if name.lower().endswith(".pdf"):
                    zf.write(os.path.join(pdf_dir, name), f"pdfs/{name}")
        legacy_dir = exe_dir
        if legacy_dir != pdf_dir and os.path.isdir(legacy_dir):
            for name in os.listdir(legacy_dir):
                if name.lower().endswith(".pdf"):
                    arc = f"pdfs/{name}"
                    if arc not in zf.namelist():
                        zf.write(os.path.join(legacy_dir, name), arc)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    buf.seek(0)
    return buf, stamp


def _save_with_webview(default_name):
    from desktop_shell import get_main_window

    import webview

    window = get_main_window()
    if window is None:
        raise BackupExportError("Desktop window is not ready.")

    result = window.create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=default_name,
        file_types=("ZIP archives (*.zip)", "All files (*.*)"),
    )
    if not result:
        return None
    if isinstance(result, (list, tuple)):
        return result[0] if result else None
    return str(result)


def _save_with_tk(default_name):
    if sys.platform != "win32":
        raise BackupExportError("Save dialog is only supported on Windows.")

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update_idletasks()
    path = filedialog.asksaveasfilename(
        title="Save backup",
        defaultextension=".zip",
        initialfile=default_name,
        filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
    )
    root.destroy()
    return path if path else None


def pick_save_path(default_name):
    from desktop_shell import is_desktop_mode

    if is_desktop_mode():
        return _save_with_webview(default_name)
    return _save_with_tk(default_name)


def save_backup_to_path(buf, path):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(buf.getvalue())


def export_backup_with_dialog(exe_dir):
    """
    Prompt for a save location and write the backup ZIP.
    Returns the saved path, or None if the user cancelled.
    """
    buf, stamp = build_backup_zip(exe_dir)
    default_name = f"FrogsWork-backup_{stamp}.zip"
    path = pick_save_path(default_name)
    if not path:
        return None
    if not path.lower().endswith(".zip"):
        path += ".zip"
    save_backup_to_path(buf, path)
    return path
