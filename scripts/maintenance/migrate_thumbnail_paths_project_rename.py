#!/usr/bin/env python3
"""
Rename stored project root in thumbnail-related columns after moving the repo
(e.g. image-scoring -> image-scoring-backend).

Updates:
  - images.thumbnail_path   (WSL-style paths under your configured prefix)
  - images.thumbnail_path_win (Windows-style paths)
  - images.scores_json      (text blob: path strings inside JSON)

Does not change images.file_path (use other tools if you moved photo roots).

Configuration: copy migrate_thumbnail_paths.config.example.json to
migrate_thumbnail_paths.config.json (gitignored) and edit paths to match your DB.

Usage (from project root, WSL + ~/.venvs/tf per project rules):
  python scripts/maintenance/migrate_thumbnail_paths_project_rename.py --config scripts/maintenance/migrate_thumbnail_paths.config.json
  python scripts/maintenance/migrate_thumbnail_paths_project_rename.py --config ... --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.db import connection  # noqa: E402


def _load_config(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _replace_scores_json(text: str, cfg: dict) -> str:
    """Replace project-root path segments inside JSON (WSL + Windows)."""
    s = text.replace(cfg["old_wsl_root"], cfg["new_wsl_root"])
    s = s.replace(cfg["scores_json_old_win_slash"], cfg["scores_json_new_win_slash"])
    s = s.replace(cfg["scores_json_old_win_backslash"], cfg["scores_json_new_win_backslash"])
    return s


def run(dry_run: bool, cfg: dict) -> None:
    old_wsl_thumb = cfg["old_wsl_thumb_prefix"]
    new_wsl_thumb = cfg["new_wsl_thumb_prefix"]
    old_wsl_root = cfg["old_wsl_root"]
    old_win_scores = cfg["scores_json_old_win_slash"]

    with connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COUNT(*) FROM images
            WHERE thumbnail_path IS NOT NULL
              AND thumbnail_path CONTAINING ?
            """,
            (old_wsl_thumb,),
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
                OR scores_json CONTAINING ?
              )
            """,
            (old_wsl_root, old_win_scores),
        )
        n_scores = cur.fetchone()[0]
        print(f"rows with SCORES_JSON to scan (WSL or Windows old root): {n_scores}")

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
                (old_wsl_thumb, new_wsl_thumb, old_wsl_thumb),
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
                    cfg["old_win_thumb_backslash"],
                    cfg["new_win_thumb_backslash"],
                    cfg["old_win_thumb_backslash"],
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
                    cfg["old_win_thumb_slash"],
                    cfg["new_win_thumb_slash"],
                    cfg["old_win_thumb_slash"],
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
                    OR scores_json CONTAINING ?
                  )
                """,
                (old_wsl_root, old_win_scores),
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
                new_text = _replace_scores_json(text, cfg)
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
        "--config",
        type=Path,
        required=True,
        help="Path to JSON config (see migrate_thumbnail_paths.config.example.json).",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run only).",
    )
    args = ap.parse_args()
    cfg = _load_config(args.config)
    dry_run = not args.apply
    run(dry_run=dry_run, cfg=cfg)


if __name__ == "__main__":
    main()
