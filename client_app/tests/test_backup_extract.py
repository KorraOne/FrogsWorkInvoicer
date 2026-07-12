"""Tests for secure backup ZIP extraction."""

import io
import os
import zipfile

import pytest

from app_platform.backup_extract import extract_backup_zip


def _zip_with_member(name: str, content: bytes = b"x") -> zipfile.ZipFile:
    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, "w")
    zf.writestr(name, content)
    zf.close()
    buf.seek(0)
    return zipfile.ZipFile(buf, "r")


def test_extract_skips_traversal_paths(tmp_path):
    data_path = tmp_path / "data"
    pdf_dir = tmp_path / "pdfs"
    os.makedirs(data_path)
    zf = _zip_with_member("../evil.json")
    extract_backup_zip(zf, data_path=str(data_path), pdf_dir=str(pdf_dir))
    assert not (data_path / "evil.json").exists()
    assert not (tmp_path / "evil.json").exists()


def test_extract_allows_safe_root_json(tmp_path):
    data_path = tmp_path / "data"
    pdf_dir = tmp_path / "pdfs"
    os.makedirs(data_path)
    zf = _zip_with_member("customers.json", b"{}")
    extract_backup_zip(zf, data_path=str(data_path), pdf_dir=str(pdf_dir))
    assert (data_path / "customers.json").exists()


def test_extract_rejects_unsafe_attachment_path(tmp_path):
    data_path = tmp_path / "data"
    pdf_dir = tmp_path / "pdfs"
    os.makedirs(data_path)
    zf = _zip_with_member("attachments/../00000001/secret.pdf", b"%PDF-1.4")
    extract_backup_zip(zf, data_path=str(data_path), pdf_dir=str(pdf_dir))
    assert not list((data_path / "attachments").rglob("*")) if (data_path / "attachments").exists() else True
