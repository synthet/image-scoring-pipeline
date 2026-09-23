"""Build the pinned, stratified cohort for the detector benchmark (#377).

Read-only against the library database: nothing here writes ``images.bird_bbox`` or any
other table. Run in ``image-scoring-gpu-shell``:

    python scripts/research/detector_benchmark/build_cohort.py --out <dir>

Why stratified, and why these strata
------------------------------------
The detector's own labelled validation set cannot measure the failure under study: its
smallest box covers 0.0597 of the frame and it has no negatives, while the missed eagle
frames sit near 0.014. So the cohort comes from the library, and a human labels presence.

Three strata are drawn from what the *production* detector already returned, split by
subject size. They are biased by that detector by construction -- a frame it never fired
on cannot land in a "detected" stratum -- so the report states recall per stratum and
never pools them into one library-wide rate. Two strata come from frames it did *not*
fire on, split by whether tagging thought a bird was present. The one without any bird,
wildlife or animal keyword is the source of verified negatives.

The 59-frame eagle folder (2026-08-23) is excluded here and carried as its own
regression slice, so it cannot dominate the sampled strata.

Sampling is ``ORDER BY md5(id || seed)`` -- deterministic for a given seed and database
state, and independent of insertion order. At most ``--per-folder`` frames come from any
one folder, so a single large shoot cannot supply a whole stratum.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("build_cohort")

#: keywords_dim ids resolved by name at run time; these are the names.
BIRD_KEYWORD = "birds"
NEGATIVE_EXCLUDE_KEYWORDS = ("birds", "wildlife", "animals")

EAGLE_FOLDER = "/mnt/d/Photos/Z8/180-600mm/2026/2026-08-23/"

#: (name, n, SQL predicate on images i). Predicates must be read-only expressions.
STRATA = [
    ("det_small", 50, "i.bird_bbox ? 'x1' AND (i.bird_bbox->>'area_frac')::float < 0.04"),
    ("det_medium", 50, "i.bird_bbox ? 'x1' AND (i.bird_bbox->>'area_frac')::float >= 0.04"
                       " AND (i.bird_bbox->>'area_frac')::float < 0.15"),
    ("det_large", 30, "i.bird_bbox ? 'x1' AND (i.bird_bbox->>'area_frac')::float >= 0.15"),
    ("miss_birdkw", 90, "i.bird_bbox->>'detected' = 'false' AND NOT i.bird_bbox ? 'error'"
                        " AND EXISTS (SELECT 1 FROM image_keywords k"
                        "             WHERE k.image_id = i.id AND k.keyword_id = %(bird_kw)s)"),
    ("miss_nokw", 60, "i.bird_bbox->>'detected' = 'false' AND NOT i.bird_bbox ? 'error'"
                      " AND NOT EXISTS (SELECT 1 FROM image_keywords k"
                      "                 WHERE k.image_id = i.id AND k.keyword_id = ANY(%(neg_kw)s))"),
]

FIELDS = ["image_id", "stratum", "file_path", "folder_id", "stored_state",
          "stored_area_frac", "stored_conf", "thumbnail_path"]


def _connect():
    import psycopg2

    from modules import db_postgres

    cfg = db_postgres.get_pg_config()
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
                            user=cfg["user"], password=cfg["password"])
    conn.set_session(readonly=True)  # belt and braces: this script must never write
    return conn


def _keyword_ids(cur, names):
    cur.execute("SELECT keyword_norm, keyword_id FROM keywords_dim WHERE keyword_norm = ANY(%s)",
                (list(names),))
    found = dict(cur.fetchall())
    missing = [n for n in names if n not in found]
    if missing:
        raise SystemExit(f"keywords_dim is missing {missing}; refusing to guess ids")
    return found


def _sample(cur, name, n, predicate, params, seed, per_folder):
    sql = f"""
        WITH ranked AS (
            SELECT i.id, i.file_path, i.folder_id, i.bird_bbox, i.thumbnail_path,
                   row_number() OVER (PARTITION BY i.folder_id
                                      ORDER BY md5(i.id::text || %(seed)s)) AS rn_in_folder
            FROM images i
            WHERE {predicate}
              AND i.file_path NOT LIKE %(eagle)s
              AND lower(i.file_path) LIKE '%%.nef'
        )
        SELECT id, file_path, folder_id, bird_bbox, thumbnail_path
        FROM ranked
        WHERE rn_in_folder <= %(per_folder)s
        ORDER BY md5(id::text || %(seed)s)
        LIMIT %(n)s
    """
    cur.execute(sql, {**params, "seed": str(seed), "eagle": EAGLE_FOLDER + "%",
                      "per_folder": per_folder, "n": n})
    rows = []
    for image_id, path, folder_id, bbox, thumb in cur.fetchall():
        bbox = bbox or {}
        rows.append({
            "image_id": image_id,
            "stratum": name,
            "file_path": path,
            "folder_id": folder_id,
            "stored_state": "box" if "x1" in bbox else "no_detection",
            "stored_area_frac": bbox.get("area_frac", ""),
            "stored_conf": bbox.get("conf", ""),
            "thumbnail_path": thumb or "",
        })
    if len(rows) < n:
        logger.warning("stratum %s: wanted %d, got %d", name, n, len(rows))
    return rows


def _eagle_slice(cur, comparison_csv):
    """The 59 frames of the Sept 7 audit, by stem -> NEF in the eagle folder."""
    with open(comparison_csv, newline="", encoding="utf-8") as fh:
        stems = [r["stem"] for r in csv.DictReader(fh)]
    cur.execute("""SELECT id, file_path, folder_id, bird_bbox, thumbnail_path FROM images
                   WHERE file_path = ANY(%s)""",
                ([f"{EAGLE_FOLDER}{s}.NEF" for s in stems],))
    by_path = {r[1]: r for r in cur.fetchall()}
    rows = []
    for s in stems:
        r = by_path.get(f"{EAGLE_FOLDER}{s}.NEF")
        if r is None:
            logger.warning("eagle stem %s not found in images", s)
            continue
        image_id, path, folder_id, bbox, thumb = r
        bbox = bbox or {}
        rows.append({
            "image_id": image_id, "stratum": "eagle", "file_path": path,
            "folder_id": folder_id,
            "stored_state": "box" if "x1" in bbox else "no_detection",
            "stored_area_frac": bbox.get("area_frac", ""),
            "stored_conf": bbox.get("conf", ""),
            "thumbnail_path": thumb or "",
        })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="Directory for cohort.csv")
    ap.add_argument("--seed", type=int, default=377)
    ap.add_argument("--per-folder", type=int, default=3)
    ap.add_argument("--eagle-csv", required=True,
                    help="image-scoring-skills work/disk/A41/score/comparison.csv")
    ap.add_argument("--dry-run", action="store_true", help="Print stratum counts, write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    conn = _connect()
    try:
        with conn.cursor() as cur:
            ids = _keyword_ids(cur, set(NEGATIVE_EXCLUDE_KEYWORDS) | {BIRD_KEYWORD})
            params = {"bird_kw": ids[BIRD_KEYWORD],
                      "neg_kw": [ids[k] for k in NEGATIVE_EXCLUDE_KEYWORDS]}
            rows = []
            for name, n, pred in STRATA:
                rows += _sample(cur, name, n, pred, params, args.seed, args.per_folder)
            rows += _eagle_slice(cur, args.eagle_csv)
    finally:
        conn.close()

    counts = {}
    for r in rows:
        counts[r["stratum"]] = counts.get(r["stratum"], 0) + 1
    for name, n in counts.items():
        logger.info("  %-12s %d", name, n)
    ids_seen = [r["image_id"] for r in rows]
    if len(ids_seen) != len(set(ids_seen)):
        raise SystemExit("duplicate image_id across strata -- predicates overlap")
    if args.dry_run:
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "cohort.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    logger.info("wrote %d rows to %s", len(rows), out / "cohort.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
