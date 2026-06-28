"""Windows folder picker — pywebview dialog in desktop mode, tkinter queue otherwise."""

import queue
import sys

_pick_requests = queue.Queue()


class FolderPickerError(Exception):
    pass


class FolderPickerTimeout(FolderPickerError):
    pass


def _pick_with_webview(title):
    from desktop_shell import get_main_window

    import webview

    window = get_main_window()
    if window is None:
        raise FolderPickerError("Desktop window is not ready.")

    result = window.create_file_dialog(
        webview.FOLDER_DIALOG,
        directory="",
        allow_multiple=False,
    )
    if not result:
        return None
    if isinstance(result, (list, tuple)):
        return result[0] if result else None
    return str(result)


def _show_tk_dialog(title):
    if sys.platform != "win32":
        raise FolderPickerError("Folder picker is only supported on Windows.")

    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update_idletasks()
    path = filedialog.askdirectory(title=title, mustexist=True, parent=root)
    root.destroy()
    return path if path else None


def pick_folder(title="Choose a folder", timeout=300):
    from desktop_shell import is_desktop_mode

    if is_desktop_mode():
        return _pick_with_webview(title)

    request_id = object()
    result_q = queue.Queue(maxsize=1)
    _pick_requests.put((request_id, title, result_q))
    try:
        path, err = result_q.get(timeout=timeout)
    except queue.Empty as exc:
        raise FolderPickerTimeout("Folder picker timed out.") from exc
    if err:
        raise FolderPickerError(err)
    return path


def process_pending_picks():
    """Process one pending folder pick (dev-browser mode main loop only)."""
    try:
        _request_id, title, result_q = _pick_requests.get_nowait()
    except queue.Empty:
        return
    try:
        path = _show_tk_dialog(title)
        result_q.put((path, None))
    except Exception as exc:
        result_q.put((None, str(exc)))
