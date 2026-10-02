"""Image file-path registration and Windows viewer path resolution."""

import datetime
import logging
from collections.abc import Callable
from typing import Any


def register_image_path(image_id, path, *, get_connector: Callable[[], Any]):
    """
    Registers a path for a given image ID (default type='WSL').
    """
    path_type = "WSL"
    try:
        get_connector().execute(
            "UPDATE OR INSERT INTO file_paths (image_id, path, path_type, last_seen) VALUES (?, ?, ?, ?) MATCHING (image_id, path)",
            (image_id, path, path_type, datetime.datetime.now()),
        )
    except Exception as e:
        logging.error(f"Failed to register path {path} for image {image_id}: {e}")


def get_all_paths(image_id, *, get_connector: Callable[[], Any]):
    rows = get_connector().query(
        "SELECT path FROM file_paths WHERE image_id = ?", (image_id,)
    )
    return [r["path"] for r in rows]


# --- Resolved Paths (Windows Native Viewer Support) ---


def resolve_windows_path(
    image_id,
    wsl_path,
    verify=True,
    *,
    get_connector: Callable[[], Any],
    to_windows: Callable[[str], str],
):
    """
    Resolves a WSL/Unix path to Windows format and stores in file_paths (type='WIN').
    """
    import platform

    windows_path = to_windows(wsl_path)
    if not windows_path:
        return None

    # Verify file exists (if on Windows)
    is_verified = 0
    verification_date = None
    now = datetime.datetime.now()

    if verify and platform.system() == "Windows":
        import os

        if os.path.exists(windows_path):
            is_verified = 1
            verification_date = now

    if image_id is None:
        return windows_path

    try:
        # Same path may already exist as path_type=WSL from register_image_path; uq_file_paths_image_id_path
        # is on (image_id, path) so we must upgrade that row instead of inserting a second WIN row.
        row_same_path = get_connector().query_one(
            "SELECT id FROM file_paths WHERE image_id = ? AND path = ?",
            (image_id, windows_path),
        )
        if row_same_path:
            get_connector().execute(
                "UPDATE file_paths SET path_type = 'WIN', is_verified = ?, verification_date = ?, last_seen = ? WHERE id = ?",
                (is_verified, verification_date, now, row_same_path["id"]),
            )
            return windows_path
        row_win = get_connector().query_one(
            "SELECT id FROM file_paths WHERE image_id = ? AND path_type = 'WIN'",
            (image_id,),
        )
        if row_win:
            get_connector().execute(
                "UPDATE file_paths SET path = ?, is_verified = ?, verification_date = ?, last_seen = ? WHERE id = ?",
                (windows_path, is_verified, verification_date, now, row_win["id"]),
            )
        else:
            get_connector().execute(
                "INSERT INTO file_paths (image_id, path, path_type, is_verified, verification_date, last_seen) VALUES (?, ?, 'WIN', ?, ?, ?)",
                (image_id, windows_path, is_verified, verification_date, now),
            )
        return windows_path
    except Exception as e:
        logging.error(f"Failed to resolve path for image {image_id}: {e}")
        return None


def get_resolved_path(
    image_id, verified_only=True, *, get_connector: Callable[[], Any]
):
    """
    Returns the Windows path for an image from file_paths (type='WIN').
    """
    query = "SELECT path FROM file_paths WHERE image_id = ? AND path_type = 'WIN'"
    if verified_only:
        query += " AND is_verified = 1"
    row = get_connector().query_one(query, (image_id,))
    return row["path"] if row else None


def verify_resolved_path(image_id, *, get_connector: Callable[[], Any]):
    """
    Verifies that a resolved path still exists on disk.
    """
    import os
    import platform

    if platform.system() != "Windows":
        return False

    row = get_connector().query_one(
        "SELECT id, path FROM file_paths WHERE image_id = ? AND path_type = 'WIN'",
        (image_id,),
    )
    if not row:
        return False

    rp_id = row["id"]
    windows_path = row["path"]
    now = datetime.datetime.now()
    exists = os.path.exists(windows_path)

    get_connector().execute(
        "UPDATE file_paths SET is_verified = ?, verification_date = ?, last_seen = ? WHERE id = ?",
        (1 if exists else 0, now if exists else None, now, rp_id),
    )
    return exists


def get_resolved_paths_batch(image_ids, *, get_connector: Callable[[], Any]):
    """
    Get resolved Windows paths for a batch of image IDs.
    Returns a dictionary mapping image_id -> windows_path.
    Only returns verified paths that are correctly formatted.
    """
    if not image_ids:
        return {}

    placeholders = ",".join(["?"] * len(image_ids))
    query = f"SELECT image_id, path FROM file_paths WHERE image_id IN ({placeholders}) AND path_type = 'WIN' AND is_verified = 1"
    rows = get_connector().query(query, tuple(image_ids))

    result = {}
    for row in rows:
        path = row["path"]
        # Ensure path is truly Windows format (backslashes)
        # Mixed separators can cause "file not found" in some Windows APIs
        if path and "/" not in path:
            result[row["image_id"]] = path
    return result
