#!/usr/bin/env python3
"""
List folders that have images but no stack assignments, optionally enqueue clustering jobs.

Matches the plan in docs: folders where SUM(stack_id IS NOT NULL) = 0 per folder.

Usage (WSL, project root, venv per CLAUDE.md):
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/...
  source ~/.venvs/tf/bin/activate
  python scripts/maintenance/queue_clustering_no_stacks_folders.py --output-json /tmp/folders_no_stacks.json

  python scripts/maintenance/queue_clustering_no_stacks_folders.py --enqueue --limit 5

Requires WebUI / JobDispatcher for queued jobs to run (--enqueue).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


QUERY_DEFAULT = """
SELECT f.id, f.path,
       COUNT(i.id) AS image_count,
       SUM(CASE WHEN i.stack_id IS NOT NULL THEN 1 ELSE 0 END) AS stacked_count
FROM folders f
JOIN images i ON i.folder_id = f.id
GROUP BY f.id, f.path
HAVING SUM(CASE WHEN i.stack_id IS NOT NULL THEN 1 ELSE 0 END) = 0
{extra_having}
ORDER BY COUNT(i.id) DESC
"""

QUERY_CULLING_DONE = """
SELECT f.id, f.path,
       COUNT(i.id) AS image_count,
       SUM(CASE WHEN i.stack_id IS NOT NULL THEN 1 ELSE 0 END) AS stacked_count
FROM folders f
JOIN images i ON i.folder_id = f.id
GROUP BY f.id, f.path
HAVING SUM(CASE WHEN i.stack_id IS NOT NULL THEN 1 ELSE 0 END) = 0
AND NOT EXISTS (
    SELECT 1 FROM images i2
    WHERE i2.folder_id = f.id
      AND NOT EXISTS (
          SELECT 1 FROM image_phase_status ips
          JOIN pipeline_phases pp ON pp.id = ips.phase_id AND pp.code = 'culling'
          WHERE ips.image_id = i2.id AND ips.status = 'done'
      )
)
{extra_having}
ORDER BY COUNT(i.id) DESC
"""


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        rid = row.get("id") or row.get("ID")
        path = row.get("path") or row.get("PATH")
        ic = row.get("image_count") or row.get("IMAGE_COUNT")
        sc = row.get("stacked_count") or row.get("STACKED_COUNT")
        return {
            "id": rid,
            "path": path,
            "image_count": int(ic or 0),
            "stacked_count": int(sc or 0),
        }
    return {
        "id": row[0],
        "path": row[1],
        "image_count": int(row[2] or 0),
        "stacked_count": int(row[3] or 0),
    }


def fetch_folders(
    min_images: int = 1,
    require_culling_done: bool = False,
) -> list[dict[str, Any]]:
    from modules import db

    db.init_db()
    extra_having = ""
    if min_images > 1:
        extra_having = f"AND COUNT(i.id) >= {int(min_images)}"

    sql = (QUERY_CULLING_DONE if require_culling_done else QUERY_DEFAULT).format(
        extra_having=extra_having
    )
    conn = db.get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    finally:
        conn.close()

    out = []
    for row in rows:
        d = _row_to_dict(row)
        out.append(d)
    return out


def _path_exists_any_form(path: str) -> bool:
    if not path:
        return False
    if os.path.exists(path):
        return True
    try:
        from modules import utils

        if os.name == "nt":
            local = utils.convert_path_to_local(path)
            if local != path and os.path.exists(local):
                return True
        else:
            wsl = utils.convert_path_to_wsl(path)
            if wsl != path and os.path.exists(wsl):
                return True
    except Exception:
        pass
    return False


def enqueue_clustering_for_folder(
    folder_path: str,
    *,
    threshold: float | None,
    time_gap: int | None,
    force_rescan: bool,
    recursive: bool,
) -> tuple[int | None, int, int]:
    """Returns (job_id, queue_position, resolved_count). job_id None on failure."""
    from modules import db
    from modules.selector_resolver import resolve_selectors

    selector_result = resolve_selectors(
        folder_paths=[folder_path],
        recursive=recursive,
        index_missing=True,
    )
    resolved = selector_result.get("resolved_image_ids") or []
    resolved_count = len(resolved)
    if not resolved:
        return None, 0, 0

    payload_input_path: str | None = folder_path
    if not _path_exists_any_form(folder_path):
        payload_input_path = None

    job_id, queue_position = db.enqueue_job(
        folder_path or "SELECTOR_CLUSTERING",
        phase_code="culling",
        job_type="clustering",
        queue_payload={
            "input_path": payload_input_path,
            "threshold": threshold,
            "time_gap": time_gap,
            "force_rescan": force_rescan,
            "resolved_image_ids": resolved,
        },
    )
    if job_id is not None:
        db.create_job_phases(job_id, ["culling"], first_phase_state="queued")
    return job_id, queue_position, resolved_count


def summarize_no_stacks(folders: list[dict[str, Any]]) -> dict[str, Any]:
    total_images = sum(f.get("image_count", 0) for f in folders)
    return {
        "folder_count": len(folders),
        "total_images_in_those_folders": total_images,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="List folders with no stacks; optionally enqueue clustering jobs.")
    p.add_argument("--min-images", type=int, default=1, help="Minimum images per folder (default 1). Use 2 for stricter.")
    p.add_argument(
        "--require-culling-done",
        action="store_true",
        help="Only folders where every image has culling phase status done.",
    )
    p.add_argument("--output-json", type=str, default=None, help="Write folder list JSON to this path.")
    p.add_argument("--enqueue", action="store_true", help="Enqueue clustering job per folder (needs WebUI dispatcher).")
    p.add_argument("--limit", type=int, default=0, help="Max folders to enqueue (0 = all).")
    p.add_argument("--recursive", action="store_true", help="Pass recursive=True to resolve_selectors (default off).")
    p.add_argument("--threshold", type=float, default=None, help="Clustering distance threshold (default from config).")
    p.add_argument("--time-gap", type=int, default=None, help="Time gap seconds (default from config).")
    p.add_argument(
        "--no-force-rescan",
        action="store_true",
        help="Do not set force_rescan (default is True for re-clustering done folders).",
    )
    p.add_argument("--verify", action="store_true", help="Print summary counts only (same query; for before/after checks).")
    p.add_argument(
        "--folder-stack-status",
        type=int,
        metavar="FOLDER_ID",
        help="Print image count and how many have stack_id set for this folder (after clustering completes).",
    )
    args = p.parse_args()

    if args.folder_stack_status is not None:
        from modules import db

        db.init_db()
        conn = db.get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT path FROM folders WHERE id = ?",
                (args.folder_stack_status,),
            )
            prow = cur.fetchone()
            if not prow:
                path = None
            elif isinstance(prow, dict):
                path = prow.get("path") or prow.get("PATH")
            else:
                path = prow[0]
            cur.execute(
                """
                SELECT COUNT(*), SUM(CASE WHEN stack_id IS NOT NULL THEN 1 ELSE 0 END)
                FROM images WHERE folder_id = ?
                """,
                (args.folder_stack_status,),
            )
            row = cur.fetchone()
            if isinstance(row, dict):
                total = int(row.get("count") or row.get("COUNT") or 0)
                stacked = int(row.get("sum") or row.get("SUM") or 0)
            else:
                total, stacked = int(row[0] or 0), int(row[1] or 0)
            print(json.dumps({"folder_id": args.folder_stack_status, "path": path, "images": total, "with_stack": stacked}, indent=2))
        finally:
            conn.close()
        return 0

    try:
        rows = fetch_folders(
            min_images=args.min_images,
            require_culling_done=args.require_culling_done,
        )
    except Exception as e:
        logger.error("Database query failed: %s", e)
        return 1

    summary = summarize_no_stacks(rows)
    if args.verify:
        print(json.dumps({"mode": "verify", **summary}, indent=2))
        if args.output_json:
            out_path = os.path.abspath(args.output_json)
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"folders": rows, "summary": {**summary, "mode": "verify"}}, f, indent=2)
            print(f"Wrote {out_path}")
        return 0

    print(f"Folders with no stack assignments: {summary['folder_count']}")
    print(f"Total images in those folders: {summary['total_images_in_those_folders']}")

    if args.output_json:
        out_path = os.path.abspath(args.output_json)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"folders": rows, "summary": summary}, f, indent=2)
        print(f"Wrote {out_path}")

    if not args.enqueue:
        for i, r in enumerate(rows[:50]):
            print(f"  {r['id']}\t{r['image_count']}\t{r['path']}")
        if len(rows) > 50:
            print(f"  ... and {len(rows) - 50} more (not printed)")

    if not args.enqueue:
        return 0

    force_rescan = not args.no_force_rescan
    limit = args.limit if args.limit > 0 else len(rows)
    to_run = rows[:limit]
    ok = 0
    for r in to_run:
        path = r.get("path")
        if not path:
            continue
        jid, pos, nres = enqueue_clustering_for_folder(
            path,
            threshold=args.threshold,
            time_gap=args.time_gap,
            force_rescan=force_rescan,
            recursive=args.recursive,
        )
        if jid is None:
            logger.warning("Skip (no images resolved): %s", path)
            continue
        logger.info("Queued job_id=%s position=%s images=%s path=%s", jid, pos, nres, path)
        ok += 1
    print(f"Enqueued {ok} clustering job(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
