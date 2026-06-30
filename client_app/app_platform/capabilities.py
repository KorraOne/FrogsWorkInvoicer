"""Runtime capability detection for OS and deployment mode."""

import sys


def is_windows():
    return sys.platform == "win32"


def is_packaged():
    return getattr(sys, "frozen", False)


def is_desktop():
    from desktop_shell import is_desktop_mode

    return is_desktop_mode()
