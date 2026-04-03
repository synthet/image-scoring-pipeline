"""
Tests for thumbnail path helpers: nested layout, get_thumb_wsl/get_thumb_win, conversions.
No DB or sample files required.
"""
import os
import sys

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import thumbnails


def test_get_thumb_path_nested_layout():
    """get_thumb_path returns path under thumbnails/{hash[:2]}/{hash}.jpg."""
    path = "/mnt/x/Photos/test/image.NEF"
    result = thumbnails.get_thumb_path(path)
    assert result is not None
    assert result.endswith(".jpg")
    base = os.path.basename(result)
    stem = base[:-4]
    assert len(stem) == 32
    parent = os.path.basename(os.path.dirname(result))
    assert parent == stem[:2]
    assert result.startswith(thumbnails.THUMB_DIR)


def test_thumb_path_to_win():
    """WSL path converts to Windows path."""
    wsl = "/mnt/x/ws/thumbnails/ab/abcdef0123456789.jpg"
    win = thumbnails.thumb_path_to_win(wsl)
    assert win is not None
    assert "\\" in win or win.startswith("X:")
    assert "ab" in win and "abcdef0123456789.jpg" in win


def test_thumb_path_to_wsl():
    """Windows path converts to WSL path."""
    win = r"X:\ws\thumbnails\ab\abcdef0123456789.jpg"
    wsl = thumbnails.thumb_path_to_wsl(win)
    assert wsl is not None
    assert wsl.startswith("/mnt/")
    assert "/ab/abcdef0123456789.jpg" in wsl


def test_get_thumb_wsl_prefers_thumbnail_path():
    """get_thumb_wsl returns thumbnail_path when set."""
    row = {"thumbnail_path": "/mnt/x/thumbnails/ab/ab123.jpg", "thumbnail_path_win": r"X:\thumbnails\ab\ab123.jpg"}
    assert thumbnails.get_thumb_wsl(row) == "/mnt/x/thumbnails/ab/ab123.jpg"


def test_get_thumb_wsl_fallback_from_win():
    """get_thumb_wsl converts thumbnail_path_win when thumbnail_path empty."""
    row = {"thumbnail_path": None, "thumbnail_path_win": r"X:\thumbnails\ab\ab123.jpg"}
    result = thumbnails.get_thumb_wsl(row)
    assert result is not None
    assert result.startswith("/mnt/")


def test_get_thumb_win_prefers_thumbnail_path_win():
    """get_thumb_win returns thumbnail_path_win when set."""
    row = {"thumbnail_path": "/mnt/x/thumbnails/ab/ab123.jpg", "thumbnail_path_win": r"X:\thumbnails\ab\ab123.jpg"}
    assert thumbnails.get_thumb_win(row) == r"X:\thumbnails\ab\ab123.jpg"


def test_get_thumb_win_fallback_from_wsl():
    """get_thumb_win converts thumbnail_path when thumbnail_path_win empty."""
    row = {"thumbnail_path": "/mnt/x/ws/thumbnails/ab/ab123.jpg", "thumbnail_path_win": None}
    result = thumbnails.get_thumb_win(row)
    assert result is not None
    assert "\\" in result or result.startswith("X:")


def test_get_local_thumb_uses_platform():
    """get_local_thumb returns wsl or win path based on platform."""
    row = {"thumbnail_path": "/mnt/x/t.jpg", "thumbnail_path_win": r"X:\t.jpg"}
    result = thumbnails.get_local_thumb(row)
    assert result is not None
    if os.name == "nt":
        assert result == r"X:\t.jpg"
    else:
        assert result == "/mnt/x/t.jpg"


def test_consumers_import_and_call_get_thumb_wsl():
    """Consumer modules can import thumbnails and call get_thumb_wsl with a row-like dict."""
    row = {
        "id": 1,
        "thumbnail_path": "/mnt/x/ws/thumbnails/ab/abcdef1234567890.jpg",
        "thumbnail_path_win": r"thumbnails\ab\abcdef1234567890.jpg",
    }
    wsl = thumbnails.get_thumb_wsl(row)
    win = thumbnails.get_thumb_win(row)
    assert wsl == row["thumbnail_path"]
    assert win == row["thumbnail_path_win"]
