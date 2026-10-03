"""Folder cache deletion operations with call-time connector injection."""

import logging
import os
from collections.abc import Callable
from typing import Any


def delete_folder_cache_entry(
    folder_path: str,
    delete_descendants: bool = True,
    *,
    get_connector: Callable[[], Any],
) -> dict:
    """
    Delete a folder record from the `folders` table (folder tree cache).

    **Maintenance / batch use:** this clears ``images.folder_id`` before deleting rows.
    For UI deletes of *empty* subtrees, prefer ``delete_empty_folder_cache_subtree`` (no image rows).

    This is intended for removing stale/incorrect folder cache entries that appear
    in the Folder Tree UI.

    Behavior:
    - Deletes the matching folder row(s) (supports Windows or WSL path input)
    - Optionally deletes all descendant folders (via parent_id traversal)
    - Clears `images.folder_id` for images referencing deleted folders
    - Attempts to delete matching `cluster_progress` rows (best-effort)

    Returns:
        dict with keys: success (bool), message (str), deleted_folders (int)
    """
    if not folder_path or not str(folder_path).strip():
        return {
            "success": False,
            "message": "No folder path provided.",
            "deleted_folders": 0,
        }

    # Prepare candidate path representations for lookup (DB may store WSL paths)
    raw = str(folder_path).strip()
    candidates: list[str] = []
    try:
        from modules import utils

        # If it looks like a Windows path, convert to WSL (DB convention)
        if ":" in raw or "\\" in raw:
            wsl = utils.convert_path_to_wsl(raw)
            if wsl and wsl != raw:
                candidates.append(wsl)
            candidates.append(os.path.normpath(raw))
        else:
            candidates.append(raw)
    except Exception:
        candidates.append(raw)

    # De-dup candidates while keeping order
    seen = set()
    candidates = [p for p in candidates if not (p in seen or seen.add(p))]

    try:
        result = get_connector().run_transaction(
            lambda tx: _delete_folder_cache_entry_tx(
                tx, candidates, raw, delete_descendants
            )
        )
        if isinstance(result, dict) and "success" in result:
            return result  # Early exit (not found)

        ids_deleted = result["ids_deleted"]
        paths_deleted = result["paths_deleted"]

        # Broadcast folder deletions (outside transaction)
        try:
            from modules.events import event_manager

            for path in paths_deleted:
                event_manager.broadcast_threadsafe("folder_deleted", {"path": path})
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Deleted {len(ids_deleted)} folder cache record(s).",
            "deleted_folders": len(ids_deleted),
        }
    except Exception as e:
        logging.error(f"delete_folder_cache_entry failed for {folder_path}: {e}")
        return {
            "success": False,
            "message": f"Error deleting folder cache entry: {e}",
            "deleted_folders": 0,
        }


def delete_empty_folder_cache_subtree(
    folder_path: str, *, get_connector: Callable[[], Any]
) -> dict:
    """Remove one folder subtree from ``folders`` when no ``images.folder_id`` reference it.

    Deletes the matching cache row as the subtree root; descendant ``folders`` rows are
    removed via ``ON DELETE CASCADE`` on ``folders.parent_id`` (PostgreSQL).

    Does not delete files on disk. Returns ``reason`` of ``not_found`` or ``not_empty`` on failure.
    """
    if not folder_path or not str(folder_path).strip():
        return {
            "success": False,
            "message": "No folder path provided.",
            "deleted_folders": 0,
            "reason": "invalid",
        }

    raw = str(folder_path).strip()
    candidates: list[str] = []
    try:
        from modules import utils

        if ":" in raw or "\\" in raw:
            wsl = utils.convert_path_to_wsl(raw)
            if wsl and wsl != raw:
                candidates.append(wsl)
            candidates.append(os.path.normpath(raw))
        else:
            candidates.append(raw)
    except Exception:
        candidates.append(raw)

    seen: set[str] = set()
    candidates = [p for p in candidates if not (p in seen or seen.add(p))]

    try:
        result = get_connector().run_transaction(
            lambda tx: _delete_empty_folder_cache_subtree_tx(tx, candidates, raw)
        )
        if isinstance(result, dict) and result.get("success") is False:
            return result
        if not isinstance(result, dict) or not result.get("success"):
            return {
                "success": False,
                "message": "Unexpected delete result.",
                "deleted_folders": 0,
                "reason": "error",
            }

        paths_deleted = result.get("paths_deleted") or []
        try:
            from modules.events import event_manager

            for path in paths_deleted:
                event_manager.broadcast_threadsafe("folder_deleted", {"path": path})
        except Exception:
            pass

        n = int(result.get("deleted_folders") or 0)
        return {
            "success": True,
            "message": f"Removed {n} empty folder cache record(s).",
            "deleted_folders": n,
            "reason": None,
        }
    except Exception as e:
        logging.error(
            f"delete_empty_folder_cache_subtree failed for {folder_path}: {e}"
        )
        return {
            "success": False,
            "message": f"Error removing folder cache entries: {e}",
            "deleted_folders": 0,
            "reason": "error",
        }


def _delete_folder_cache_entry_tx(tx, candidates, raw, delete_descendants):
    # Find starting folder IDs
    start_ids: list[int] = []
    start_paths: list[str] = []
    for cand in candidates:
        try:
            row = tx.query_one("SELECT id, path FROM folders WHERE path = ?", (cand,))
            if row:
                start_ids.append(int(row["id"]))
                start_paths.append(str(row["path"]))
        except Exception:
            continue

    if not start_ids:
        return {
            "success": False,
            "message": f"Folder not found in cache: {raw}",
            "deleted_folders": 0,
        }

    # Traverse descendants by parent_id to get full delete set
    ids_to_delete: list[int] = []
    paths_to_delete: list[str] = []

    queue = list(dict.fromkeys(start_ids))
    while queue:
        batch_ids = queue[:200]
        queue = queue[200:]

        # Add current batch
        for _id in batch_ids:
            if _id not in ids_to_delete:
                ids_to_delete.append(_id)

        # Collect their paths
        placeholders = ",".join(["?"] * len(batch_ids))
        for r in tx.query(
            f"SELECT id, path FROM folders WHERE id IN ({placeholders})",
            tuple(batch_ids),
        ):
            try:
                _p = str(r["path"])
                if _p not in paths_to_delete:
                    paths_to_delete.append(_p)
            except Exception:
                pass

        if not delete_descendants:
            continue

        # Find children
        child_rows = tx.query(
            f"SELECT id FROM folders WHERE parent_id IN ({placeholders})",
            tuple(batch_ids),
        )
        for r in child_rows:
            try:
                cid = int(r["id"])
                if cid not in ids_to_delete and cid not in queue:
                    queue.append(cid)
            except Exception:
                continue

    if not ids_to_delete:
        return {
            "success": False,
            "message": f"Nothing to delete for: {raw}",
            "deleted_folders": 0,
        }

    # Clear image folder_id references first (avoid dangling references)
    placeholders = ",".join(["?"] * len(ids_to_delete))
    tx.execute(
        f"UPDATE images SET folder_id = NULL WHERE folder_id IN ({placeholders})",
        tuple(ids_to_delete),
    )

    # Best-effort cleanup for cluster_progress rows
    try:
        if paths_to_delete:
            cp_ph = ",".join(["?"] * len(paths_to_delete))
            tx.execute(
                f"DELETE FROM cluster_progress WHERE folder_path IN ({cp_ph})",
                tuple(paths_to_delete),
            )
    except Exception:
        pass

    # Delete folders (children first to be safe if FK constraints are added later)
    for fid in reversed(ids_to_delete):
        tx.execute("DELETE FROM folders WHERE id = ?", (fid,))

    return {"ids_deleted": ids_to_delete, "paths_deleted": paths_to_delete}


def _delete_empty_folder_cache_subtree_tx(tx, candidates, raw):
    root_id = None
    root_row_path = None
    for cand in candidates:
        try:
            row = tx.query_one("SELECT id, path FROM folders WHERE path = ?", (cand,))
            if row:
                root_id = int(row["id"])
                root_row_path = str(row["path"])
                break
        except Exception:
            continue

    if root_id is None:
        return {
            "success": False,
            "message": f"Folder not found in cache: {raw}",
            "deleted_folders": 0,
            "reason": "not_found",
        }

    subtree_ids: list[int] = []
    paths_for_cp: list[str] = []
    queue = [root_id]
    seen_ids: set[int] = set()
    while queue:
        bid = queue.pop(0)
        if bid in seen_ids:
            continue
        seen_ids.add(bid)
        subtree_ids.append(bid)
        prow = tx.query_one("SELECT path FROM folders WHERE id = ?", (bid,))
        if prow:
            pth = str(prow.get("path") or "")
            if pth and pth not in paths_for_cp:
                paths_for_cp.append(pth)
        for ch in tx.query("SELECT id FROM folders WHERE parent_id = ?", (bid,)):
            try:
                cid = int(ch["id"])
                if cid not in seen_ids:
                    queue.append(cid)
            except Exception:
                continue

    if not subtree_ids:
        return {
            "success": False,
            "message": f"Nothing to delete for: {raw}",
            "deleted_folders": 0,
            "reason": "not_found",
        }

    placeholders = ",".join(["?"] * len(subtree_ids))
    cnt_row = tx.query_one(
        f"SELECT COUNT(*) AS c FROM images WHERE folder_id IN ({placeholders})",
        tuple(subtree_ids),
    )
    img_count = int((cnt_row or {}).get("c") or 0)
    if img_count > 0:
        return {
            "success": False,
            "message": "Folder subtree still has indexed images; remove or move images first.",
            "deleted_folders": 0,
            "reason": "not_empty",
        }

    try:
        if paths_for_cp:
            cp_ph = ",".join(["?"] * len(paths_for_cp))
            tx.execute(
                f"DELETE FROM cluster_progress WHERE folder_path IN ({cp_ph})",
                tuple(paths_for_cp),
            )
    except Exception:
        pass

    n_del = len(subtree_ids)
    tx.execute("DELETE FROM folders WHERE id = ?", (root_id,))

    return {
        "success": True,
        "deleted_folders": n_del,
        "paths_deleted": paths_for_cp,
        "root_path": root_row_path,
    }
