"""
Tests for path utilities in modules/utils.py.

Covers convert_path_to_local, convert_path_to_wsl, compute_file_hash,
resolve_file_path (all 4 strategies), and get_image_creation_time.
"""

import hashlib
import os
import platform
import pytest

from modules import utils


# ---------------------------------------------------------------------------
# convert_path_to_local
# ---------------------------------------------------------------------------

def test_convert_path_to_local_wsl_to_windows(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = utils.convert_path_to_local("/mnt/d/Photos/img.jpg")
    assert result == "D:/Photos/img.jpg"


def test_convert_path_to_local_wsl_drive_uppercase(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = utils.convert_path_to_local("/mnt/c/Users/test.nef")
    assert result == "C:/Users/test.nef"


def test_convert_path_to_local_already_windows_unchanged(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = utils.convert_path_to_local("D:/Photos/img.jpg")
    assert result == "D:/Photos/img.jpg"


def test_convert_path_to_local_windows_path_on_linux(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    result = utils.convert_path_to_local("D:/Photos/img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_local_windows_backslash_on_linux(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    result = utils.convert_path_to_local("D:\\Photos\\img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_local_native_linux_path_unchanged(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    result = utils.convert_path_to_local("/home/user/photos/img.jpg")
    assert result == "/home/user/photos/img.jpg"


# ---------------------------------------------------------------------------
# convert_path_to_wsl
# ---------------------------------------------------------------------------

def test_convert_path_to_wsl_windows_slash():
    result = utils.convert_path_to_wsl("D:/Photos/img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_wsl_windows_backslash():
    result = utils.convert_path_to_wsl("D:\\Photos\\img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_wsl_already_wsl_unchanged():
    result = utils.convert_path_to_wsl("/mnt/d/Photos/img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_wsl_linux_path_unchanged():
    result = utils.convert_path_to_wsl("/home/user/photos.jpg")
    assert result == "/home/user/photos.jpg"


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------

def test_compute_file_hash_sha256(tmp_path, monkeypatch):
    # Prevent resolve_file_path from trying DB lookups
    monkeypatch.setattr(utils, "resolve_file_path", lambda path, image_id=None: path)

    test_file = tmp_path / "sample.bin"
    content = b"hello world"
    test_file.write_bytes(content)

    result = utils.compute_file_hash(str(test_file))
    expected = hashlib.sha256(content).hexdigest()
    assert result == expected


def test_compute_file_hash_md5(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "resolve_file_path", lambda path, image_id=None: path)

    test_file = tmp_path / "sample.bin"
    content = b"test content"
    test_file.write_bytes(content)

    result = utils.compute_file_hash(str(test_file), algorithm="md5")
    expected = hashlib.md5(content).hexdigest()
    assert result == expected


def test_compute_file_hash_nonexistent_returns_none(monkeypatch):
    monkeypatch.setattr(utils, "resolve_file_path", lambda path, image_id=None: None)
    result = utils.compute_file_hash("/nonexistent/path/file.jpg")
    assert result is None


# ---------------------------------------------------------------------------
# resolve_file_path
# ---------------------------------------------------------------------------

def test_resolve_file_path_strategy2_as_is(tmp_path, monkeypatch):
    """Strategy 2: path exists as-is on filesystem."""
    test_file = tmp_path / "img.jpg"
    test_file.write_text("fake")

    result = utils.resolve_file_path(str(test_file))
    assert result == str(test_file)


def test_resolve_file_path_strategy3_converted(tmp_path, monkeypatch):
    """Strategy 3: converted path exists."""
    test_file = tmp_path / "img.jpg"
    test_file.write_text("fake")

    # Simulate: db_path doesn't exist as-is, but convert_path_to_local returns the real path
    fake_path = "/mnt/x/nonexistent/img.jpg"
    monkeypatch.setattr(utils, "convert_path_to_local", lambda p: str(test_file))

    result = utils.resolve_file_path(fake_path)
    assert result == str(test_file)


def test_resolve_file_path_returns_none_when_nothing_found(tmp_path, monkeypatch):
    """Strategy 4 (no image_id): all strategies fail -> returns None."""
    monkeypatch.setattr(utils, "convert_path_to_local", lambda p: p)

    result = utils.resolve_file_path("/nonexistent/path/that/does/not/exist.jpg")
    assert result is None


def test_resolve_file_path_strategy1_from_db(tmp_path, monkeypatch):
    """Strategy 1: resolved_paths table has a verified path."""
    test_file = tmp_path / "resolved.jpg"
    test_file.write_text("fake")

    from modules import db
    monkeypatch.setattr(db, "get_resolved_path", lambda image_id, verified_only=True: str(test_file))
    monkeypatch.setattr(utils, "convert_path_to_local", lambda p: p)

    result = utils.resolve_file_path("/some/db/path.jpg", image_id=1)
    assert result == str(test_file)


# ---------------------------------------------------------------------------
# get_image_creation_time
# ---------------------------------------------------------------------------

def test_get_image_creation_time_returns_datetime_for_missing_file():
    """Missing file should not raise — returns datetime.now() fallback."""
    import datetime
    result = utils.get_image_creation_time("/nonexistent/image.jpg")
    assert isinstance(result, datetime.datetime)


def test_get_image_creation_time_returns_datetime_for_real_file(tmp_path):
    """Real file without EXIF returns filesystem mtime as datetime."""
    import datetime
    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"fake jpeg")

    result = utils.get_image_creation_time(str(test_file))
    assert isinstance(result, datetime.datetime)
