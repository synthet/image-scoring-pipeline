"""Read-only snapshot and reproducible sampling for model selection."""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from modules.score_analytics import study


def write_json(path, value):
    path = Path(path)
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, default=str)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(text)
    else:
        path.write_text(text, encoding="utf-8")


def read_json(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_database():
    """One repeatable-read transaction; no application/label table mutations."""
    from modules.db_postgres import PGConnectionManager
    from modules.score_normalization import get_composite_weights, get_percentile_anchors

    with PGConnectionManager() as conn, conn.cursor() as cur:
        # psycopg2 starts a transaction on the first statement.  Set the
        # isolation level through the connection before opening the cursor so
        # a pooled connection that was previously used cannot reject it.
        conn.rollback()
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True, autocommit=False)
        cur.execute("""SELECT i.id, i.file_path, i.folder_id, i.stack_id, i.image_hash,
                       i.score_general, i.score_technical, i.score_aesthetic,
                       e.date_time_original, e.sub_sec_time_original,
                       CONCAT_WS(' ', e.make, e.model), e.iso
                       FROM images i LEFT JOIN image_exif e ON e.image_id=i.id ORDER BY i.id""")
        images = []
        for r in cur.fetchall():
            date = r[8]
            if date and r[9] and str(r[9]).strip().isdigit():
                date = date.replace(microsecond=0) + timedelta(seconds=float("0." + str(r[9]).strip()))
            images.append({"id": r[0], "path": r[1], "folder": r[2], "stack": r[3], "hash": r[4],
                           "scores": {k: float(v) if v is not None else None for k, v in zip(
                               ("general", "technical", "aesthetic"), r[5:8])},
                           "captured": date.isoformat() if date else None, "camera": r[10] or "unknown",
                           "iso": r[11], "session": f"{r[2]}:{date.date() if date else 'undated'}"})
        by_id = {r["id"]: r for r in images}
        cur.execute("""SELECT model_name, model_version, status, is_shadow, COUNT(*), MIN(scored_at), MAX(scored_at)
                       FROM image_model_scores GROUP BY 1,2,3,4 ORDER BY 1,2,3,4""")
        inventory = [dict(zip(("model", "version", "status", "shadow", "count", "first", "last"), r))
                     for r in cur.fetchall()]
        cur.execute("""SELECT image_id, model_name, normalized, raw_score FROM image_model_scores
                       WHERE status='success' ORDER BY image_id, model_name""")
        raw_fallbacks = Counter()
        for iid, model, normalized, raw in cur.fetchall():
            value = normalized if normalized is not None else raw
            if iid in by_id and value is not None and np.isfinite(value):
                by_id[iid]["scores"][model] = float(value)
                if normalized is None:
                    raw_fallbacks[model] += 1
        cur.execute("""SELECT ik.image_id, kd.keyword_norm FROM image_keywords ik
                       JOIN keywords_dim kd ON ik.keyword_id=kd.keyword_id
                       WHERE kd.keyword_norm IN ('bird','birds','wildlife','portrait','landscape','people')""")
        tags = defaultdict(set)
        for iid, tag in cur.fetchall():
            tags[iid].add(tag)
    for r in images:
        ts = tags[r["id"]]
        r["subject"] = "bird" if ts & {"bird", "birds"} else "people" if ts & {"portrait", "people"} else "other"
        r["light"] = "high_iso" if (r["iso"] or 0) >= 1600 else "low_iso_or_unknown"
        r["available"] = bool(r["path"] and Path(r["path"]).is_file())
    return {"created_at": datetime.now(timezone.utc).isoformat(), "images": images,
            "inventory": inventory, "raw_fallback_counts": dict(raw_fallbacks),
            "fusion": get_composite_weights(), "percentile_anchors": get_percentile_anchors(),
            "historical_timing": "Unavailable: normalized score table has no timing column",
            "session_definition": "folder and capture date; undated images grouped conservatively by folder"}


def candidate_groups(images, *, gap_seconds=0.5):
    """Full stacks and time-gap bursts; don't truncate larger groups to eligible size."""
    stacks, streams = defaultdict(list), defaultdict(list)
    for r in images:
        if r.get("stack"):
            stacks[r["stack"]].append(r)
        if r.get("captured"):
            streams[(r["folder"], r["camera"])].append(r)
    result = [{"id": f"stack:{k}", "kind": "stack", "image_ids": [r["id"] for r in sorted(
        rows, key=lambda r: (r.get("captured") or "", r["id"]))]} for k, rows in stacks.items() if len(rows) >= 2]
    existing = {frozenset(g["image_ids"]) for g in result}
    for stream in streams.values():
        stream.sort(key=lambda r: (r["captured"], r["id"]))
        bursts, current, prev = [], [], None
        for r in stream:
            t = datetime.fromisoformat(r["captured"])
            if prev is not None and (t - prev).total_seconds() > gap_seconds:
                bursts.append(current)
                current = []
            current.append(r["id"])
            prev = t
        bursts.append(current)
        for ids in bursts:
            if len(ids) >= 2 and frozenset(ids) not in existing:
                result.append({"id": f"burst:{min(ids)}", "kind": "burst", "image_ids": ids})
    return result


def make_sample(snapshot, *, singles=600, groups=300, seed=20261001, repeat_fraction=0.1):
    images = snapshot["images"]
    by_id = {r["id"]: r for r in images}
    all_groups = candidate_groups(images)
    duplicate_hashes = defaultdict(list)
    for r in images:
        if r.get("hash"):
            duplicate_hashes[r["hash"]].append(r["id"])
    components = study.connected_components(images, all_groups + [
        {"image_ids": ids} for ids in duplicate_hashes.values() if len(ids) > 1])
    available = [r for r in images if r.get("available") and r["scores"].get("general") is not None]
    boundaries = np.quantile([r["scores"]["general"] for r in available], [1/3, 2/3])
    cameras = {c for c, _ in Counter(r["camera"] for r in available).most_common(3)}
    single_pool = []
    for r in available:
        quality = int(np.searchsorted(boundaries, r["scores"]["general"]))
        camera = r["camera"] if r["camera"] in cameras else "other_camera"
        single_pool.append({"id": f"single:{r['id']}", "kind": "single", "image_ids": [r["id"]],
                            "stratum": f"{r['subject']}|q{quality}|{camera}"})
    group_pool = []
    for g in all_groups:
        if not 2 <= len(g["image_ids"]) <= 12 or not all(by_id[i].get("available") for i in g["image_ids"]):
            continue
        rows = [by_id[i] for i in g["image_ids"]]
        subject = Counter(r["subject"] for r in rows).most_common(1)[0][0]
        size = "2" if len(rows) == 2 else "3-5" if len(rows) <= 5 else "6-12"
        winners = []
        for key in ("general", "liqe", "spaq", "topiq", "refcull_composite"):
            values = [r["scores"].get(key) for r in rows]
            if all(v is not None for v in values):
                winners.append(tuple(i for i, v in enumerate(values) if v == max(values)))
        disagree = "disagree" if len(set(winners)) > 1 else "agree"
        group_pool.append({**g, "stratum": f"{g['kind']}|{subject}|{size}|{disagree}"})
    selected = study.sample_strata(single_pool, singles, seed) + study.sample_strata(group_pool, groups, seed + 1)
    rng = np.random.default_rng(seed)
    for u in selected:
        u["block"] = components[u["image_ids"][0]]
        u["split"] = study.split_for(u["block"], seed)
        u["source_id"] = u["id"]
        u["id"] = hashlib.sha256(f"{seed}:{u['id']}".encode()).hexdigest()[:16]
    rng.shuffle(selected)
    # Repeats come later so a reviewer cannot immediately recall their first answer.
    repeats = []
    for idx in rng.choice(len(selected), int(len(selected) * repeat_fraction), replace=False):
        original = selected[int(idx)]
        repeats.append({**original, "id": hashlib.sha256((original["id"] + ":repeat").encode()).hexdigest()[:16],
                        "repeat_of": original["id"]})
    return {"schema_version": 1, "seed": seed, "units": selected + repeats,
            "population": {"single": len(single_pool), "groups": len(group_pool), "all_groups": len(all_groups)},
            "design": "stratified SRS without replacement; square-root allocation; inverse-probability weights",
            "burst_gap_seconds": 0.5, "group_size_range": [2, 12],
            "limitations": ["Subjects are keyword proxies; lighting uses ISO; subject size not available in this snapshot",
                            "Coarse EXIF timestamps can merge same-second frames; reviewer may skip wrong groups",
                            "Groups larger than 12 and unavailable source files are excluded from the target population"],
            "policy": {"global_loss_margin_rho": 0.02, "culling_loss_margin_top1": 0.02,
                       "minimum_test_blocks": 30, "minimum_done_groups": 150,
                       "test_access": "selection freezes on validation before test results are computed"}}
