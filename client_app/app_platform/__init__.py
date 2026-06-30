"""OS and desktop deployment integration."""

from .capabilities import is_desktop, is_packaged, is_windows
from .paths import exe_dir, resolve_pdf_path, resource_path, user_data_dir_path

__all__ = [
    "exe_dir",
    "is_desktop",
    "is_packaged",
    "is_windows",
    "resolve_pdf_path",
    "resource_path",
    "user_data_dir_path",
]
