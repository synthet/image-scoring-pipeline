#!/usr/bin/env python3
"""
Rename stored project root in thumbnail-related columns after moving the repo
(e.g. image-scoring -> image-scoring-backend).

Updates:
  - images.thumbnail_path   (WSL /mnt/d/Projects/.../thumbnails/...)
  - images.thumbnail_path_win (Windows D:\\Projects\\...\\thumbnails\\...)
  - images.scores_json      (text blob: path strings inside JSON)

Does not change images.file_path (use other tools if you moved photo roots).

Usage (from project root, WSL + ~/.venvs/tf per project rules):
  python scripts/maintenance/migrate_thumbnail_paths_project_rename.py
  python scripts/maintenance/migrate_thumbnail_paths_project_rename.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.db import connection  # noqa: E402

# Default: same rename as user request (edit here if your paths differ)
OLD_WSL_THUMB_PREFIX = "/mnt/d/Projects/image-scoring/thumbnails/"
NEW_WSL_THUMB_PREFIX = "/mnt/d/Projects/image-scoring-backend/thumbnails/"
OLD_WSL_ROOT = "/mnt/d/Projects/image-scoring/"
NEW_WSL_ROOT = "/mnt/d/Projects/image-scoring-backend/"


def _replace_scores_json(text: str) -> str:
    """Replace project-root path segments inside JSON (WSL + Windows)."""
    s = text.replace(OLD_WSL_ROOT, NEW_WSL_ROOT)
    s = s.replace("D:/Projects/image-scoring/", "D:/Projects/image-scoring-backend/")
    s = s.replace("D:\\Projects\\image-scoring\\", "D:\\Projects\\image-scoring-backend\\")
    return s


def run(dry_run: bool) -> None:
    with connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COUNT(*) FROM images
            WHERE thumbnail_path IS NOT NULL
              AND thumbnail_path CONTAINING ?
            """,
            (OLD_WSL_THUMB_PREFIX,),
        )
        n_thumb = cur.fetchone()[0]
        print(f"rows with THUMBNAIL_PATH to update: {n_thumb}")

        cur.execute(
            """
            SELECT COUNT(*) FROM images
            WHERE thumbnail_path_win IS NOT NULL
              AND (thumbnail_path_win CONTAINING ? OR thumbnail_path_win CONTAINING ?)
            """,
            ("image-scoring\\thumbnails", "image-scoring/thumbnails"),
        )
        n_win = cur.fetchone()[0]
        print(f"rows with THUMBNAIL_PATH_WIN to update: {n_win}")

        cur.execute(
            """
            SELECT COUNT(*) FROM images
            WHERE scores_json IS NOT NULL
              AND (
                   scores_json CONTAINING ?
                OR scores_json CONTAINING 'D:/Projects/image-scoring/'
              )
            """,
            (OLD_WSL_ROOT,),
        )
        n_scores = cur.fetchone()[0]
        print(f"rows with SCORES_JSON to scan (WSL or D:/ old root): {n_scores}")

        if dry_run:
            print("\n--dry-run: no changes written. Pass --apply to commit updates.")
            return

        if n_thumb:
            cur.execute(
                """
                UPDATE images
                SET thumbnail_path = REPLACE(thumbnail_path, ?, ?)
                WHERE thumbnail_path IS NOT NULL
                  AND thumbnail_path CONTAINING ?
                """,
                (OLD_WSL_THUMB_PREFIX, NEW_WSL_THUMB_PREFIX, OLD_WSL_THUMB_PREFIX),
            )
            print(f"THUMBNAIL_PATH rows updated: {cur.rowcount}")

        if n_win:
            cur.execute(
                """
                UPDATE images
                SET thumbnail_path_win = REPLACE(thumbnail_path_win, ?, ?)
                WHERE thumbnail_path_win IS NOT NULL
                  AND thumbnail_path_win CONTAINING ?
                """,
                (
                    r"D:\Projects\image-scoring\thumbnails",
                    r"D:\Projects\image-scoring-backend\thumbnails",
                    r"D:\Projects\image-scoring\thumbnails",
                ),
            )
            n1 = cur.rowcount
            cur.execute(
                """
                UPDATE images
                SET thumbnail_path_win = REPLACE(thumbnail_path_win, ?, ?)
                WHERE thumbnail_path_win IS NOT NULL
                  AND thumbnail_path_win CONTAINING ?
                """,
                (
                    "D:/Projects/image-scoring/thumbnails",
                    "D:/Projects/image-scoring-backend/thumbnails",
                    "D:/Projects/image-scoring/thumbnails",
                ),
            )
            print(f"THUMBNAIL_PATH_WIN rows updated (batched REPLACE): {n1} + {cur.rowcount}")

        if n_scores:
            cur.execute(
                """
                SELECT id, scores_json FROM images
                WHERE scores_json IS NOT NULL
                  AND (
                       scores_json CONTAINING ?
                    OR scores_json CONTAINING 'D:/Projects/image-scoring/'
                  )
                """,
                (OLD_WSL_ROOT,),
            )
            updated = 0
            for row in cur.fetchall():
                img_id, blob = row[0], row[1]
                if blob is None:
                    continue
                if isinstance(blob, memoryview):
                    blob = blob.tobytes()
                if isinstance(blob, bytes):
                    text = blob.decode("utf-8", errors="replace")
                else:
                    text = str(blob)
                new_text = _replace_scores_json(text)
                if new_text == text:
                    continue
                cur.execute(
                    "UPDATE images SET scores_json = ? WHERE id = ?",
                    (new_text.encode("utf-8"), img_id),
                )
                updated += 1
            print(f"SCORES_JSON rows updated: {updated}")

        conn.commit()
        print("Committed.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run only).",
    )
    args = ap.parse_args()
    dry_run = not args.apply
    run(dry_run=dry_run)


if __name__ == "__main__":
    main()
