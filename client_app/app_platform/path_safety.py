"""Safe path and filename handling — reject traversal and unsafe basenames."""

from __future__ import annotations

import os
import re

PDF_MAGIC = b"%PDF-"
INVOICE_KEY_RE = re.compile(r"^\d{8}$")
UNSAFE_BASENAME_RE = re.compile(r"(^|[\\/])\.\.([\\/]|$)|[\\/]|\x00")


def is_safe_basename(name: str) -> bool:
    """Return True if name is a single path segment with no traversal."""
    if not name or not isinstance(name, str):
        return False
    decoded = _decode_percent(name)
    if decoded != name.strip():
        return False
    base = os.path.basename(decoded)
    if base != decoded:
        return False
    if UNSAFE_BASENAME_RE.search(decoded):
        return False
    if decoded in (".", ".."):
        return False
    return True


def is_safe_invoice_key(key: str) -> bool:
    return bool(key and INVOICE_KEY_RE.match(str(key)))


def safe_join(base_dir: str, *parts: str) -> str:
    """Join under base_dir; raise ValueError if result escapes base."""
    base_real = os.path.realpath(base_dir)
    joined = os.path.join(base_real, *[p for p in parts if p])
    target = os.path.realpath(joined)
    if target != base_real and not target.startswith(base_real + os.sep):
        raise ValueError("Path escapes base directory")
    return target


def is_pdf_bytes(data: bytes) -> bool:
    return bool(data) and data.startswith(PDF_MAGIC)


def _decode_percent(value: str) -> str:
    from urllib.parse import unquote

    try:
        return unquote(value)
    except Exception:
        return value
