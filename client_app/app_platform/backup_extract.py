"""Secure backup ZIP member extraction."""

from __future__ import annotations

import os
import shutil
import zipfile

from app_platform.path_safety import is_safe_basename, is_safe_invoice_key, safe_join

ALLOWED_ROOT_FILES = frozenset(
    {
        "businesses.json",
        "customers.json",
        "invoices.json",
        "settings.json",
    }
)


def _reject_zip_member(member: str) -> bool:
    if not member or member.endswith("/"):
        return True
    if member.startswith("/") or member.startswith("\\"):
        return True
    if ".." in member.replace("\\", "/").split("/"):
        return True
    return False


def extract_backup_zip(zf: zipfile.ZipFile, *, data_path: str, pdf_dir: str) -> None:
    """Extract allowed backup ZIP members; reject zip-slip paths."""
    os.makedirs(pdf_dir, exist_ok=True)
    for member in zf.namelist():
        if _reject_zip_member(member):
            continue
        norm = member.replace("\\", "/")
        if norm.startswith("pdfs/"):
            fname = os.path.basename(norm)
            if not is_safe_basename(fname) or not fname.lower().endswith(".pdf"):
                continue
            target = safe_join(pdf_dir, fname)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        elif norm.startswith("logos/"):
            fname = os.path.basename(norm)
            if not is_safe_basename(fname):
                continue
            logos_dir = os.path.join(data_path, "logos")
            os.makedirs(logos_dir, exist_ok=True)
            target = safe_join(logos_dir, fname)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        elif norm.startswith("attachments/"):
            parts = norm.split("/")
            if len(parts) < 3:
                continue
            inv_key = parts[1]
            fname = parts[-1]
            if not is_safe_invoice_key(inv_key) or not is_safe_basename(fname):
                continue
            target_dir = safe_join(data_path, "attachments", inv_key)
            os.makedirs(target_dir, exist_ok=True)
            target = safe_join(target_dir, fname)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        else:
            fname = os.path.basename(norm)
            if fname not in ALLOWED_ROOT_FILES or not is_safe_basename(fname):
                continue
            target = safe_join(data_path, fname)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
