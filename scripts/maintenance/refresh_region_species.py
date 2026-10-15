"""Refresh only frozen, selected large/medium bird regions (#593), in GPU-shell.

snapshot captures keyword metadata and images before writes. preflight validates
explicit IDs, frozen input hashes and selected geometry. run restores non-species
metadata and verifies each image before recording it in --completed. Keep dispatch
stopped and take a verified backup first. restore is metadata repair, not rollback
of species or embeddings; those require the pre-activation database backup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SELECTED_BY = "v1_regate_rule/3:a1c2e1f64b24cc79"
SPECIES_SHA256 = "dc6984a9fa305db099f7a155d1e319fdf495c0917897c2738d2c5eee79674070"
COHORT_SHA256 = "ea4fe890940024d2055856c92ead75b6a21ab25fbacfe608e51825e8742cb8d3"
FULL_SHA256 = "05f4d357622887ed3fc44543b8e605296c4e6ce7836ae970f38643819f9a6f0d"

_KW_SQL = """
    SELECT k.image_id, d.keyword_norm, k.source, k.confidence, k.relevance_weight
    FROM image_keywords k JOIN keywords_dim d ON d.keyword_id = k.keyword_id
    WHERE k.image_id IN ({})
"""
_SELECTION_SQL = """
    SELECT s.localization_run_id AS run_id, s.region_id, s.selected_by, g.x1, g.y1, g.x2, g.y2
    FROM image_localization_selections s JOIN image_regions g ON g.id = s.region_id
    WHERE s.image_id = ? AND s.detector_key = 'bird' AND s.revoked_at IS NULL
"""


def _ids(ids):
    if not isinstance(ids, list) or not ids or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("explicit nonempty positive integer image IDs required")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate image IDs")
    return ids


def _read(path, sha256=None):
    raw = path.read_bytes()
    if sha256 and hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError(f"frozen artifact hash mismatch: {path.name}")
    return json.loads(raw)


def preflight(ids, species_list: Path, cohort: Path, full: Path):
    """Reject the entire request before a job or any database write exists."""
    from modules import bird_species as bs

    _ids(ids)
    species = [ln.strip() for ln in species_list.read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.lstrip().startswith("#")]
    digest = hashlib.sha256(json.dumps(species, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if len(species) != 369 or digest != SPECIES_SHA256:
        raise ValueError("frozen 369-name species list hash mismatch")
    frozen, report = _read(cohort, COHORT_SHA256), _read(full, FULL_SHA256)
    if frozen["selected_by"] != SELECTED_BY or report["meta"]["selected_by"] != SELECTED_BY:
        raise ValueError("unvalidated cohort rule")
    if not bs.use_regions_enabled() or bs.min_confidence() != 0.5:
        raise ValueError("region mode must be enabled with the frozen 0.5 floor")
    predictions = {int(r["image_id"]): r for r in report["images"]}
    _validate_selections(ids, frozen, predictions)
    return species, predictions


def _validate_selections(ids, frozen, predictions):
    from modules import bird_species as bs
    from modules import db

    rows = {int(r["id"]): r for r in frozen["rows"]}
    identities = {int(r["image_id"]): r for r in frozen["identities"]}
    for iid in ids:
        if iid not in rows or iid not in predictions or iid not in identities:
            raise ValueError(f"image {iid} is outside the frozen large/medium cohort")
        expected = rows[iid]
        geometry = tuple(float(expected[k]) for k in ("x1", "y1", "x2", "y2"))
        if not bs.region_species_eligible(geometry):
            raise ValueError(f"small image {iid} cannot be refreshed")
        live = db.get_connector().query_one(_SELECTION_SQL, (iid,))
        if (not live or live["selected_by"] != SELECTED_BY
                or live["run_id"] != identities[iid]["localization_run_id"]
                or live["region_id"] != identities[iid]["region_id"]
                or tuple(float(live[k]) for k in ("x1", "y1", "x2", "y2")) != geometry):
            raise ValueError(f"selected geometry/identity drift for image {iid}")


def _query(ids, sql):
    from modules import db

    result = []
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        result.extend(db.get_connector().query(sql.format(",".join("?" * len(chunk))), tuple(chunk)) or [])
    return json.loads(json.dumps(result, default=str))


def _rows(ids):
    rows = _query(ids, _KW_SQL)
    for row in rows:
        for key in ("confidence", "relevance_weight"):
            if row[key] is not None:
                row[key] = float(row[key])
    return rows


def _images(ids):
    return _query(ids, "SELECT id, to_jsonb(i) AS data FROM images i WHERE id IN ({}) ORDER BY id")


def _species_state(ids):
    """Preservation proof for geometry-only promotion, including all embedding spaces."""
    return {table: _query(ids, f"SELECT * FROM {table} WHERE image_id IN ({{}}) ORDER BY image_id, id")
            for table in ("image_phase_status", "image_embeddings", "image_embeddings_512", "image_embeddings_768")}


def snapshot(ids, out: Path, *, preserve_species=False):
    _ids(ids)
    data = {"ids": ids, "rows": _rows(ids), "images": _images(ids), "preserve_species": preserve_species}
    if len(data["images"]) != len(ids):
        raise ValueError("snapshot contains missing images")
    if preserve_species:
        data["species_state"] = _species_state(ids)
    with out.open("x", encoding="utf-8") as stream:
        json.dump(data, stream)
    return {"images": len(ids), "rows": len(data["rows"])}


def restore(snap: Path, *, ids=None):
    """Restore source/confidence/relevance exactly, including NULL versus zero."""
    return _restore(_read(snap), ids=ids)


def _keyword_created_at(ids):
    """Live non-species timestamps, read before a refresh can delete the rows."""
    from modules import db

    rows = db.get_connector().query(
        "SELECT k.image_id, d.keyword_norm, k.created_at FROM image_keywords k "
        "JOIN keywords_dim d ON d.keyword_id = k.keyword_id WHERE k.image_id IN ({})".format(
            ",".join("?" * len(ids))),
        tuple(ids)) or []
    return {(int(row["image_id"]), row["keyword_norm"]): row["created_at"]
            for row in rows if not str(row["keyword_norm"]).startswith("species:")}


def _restore(data, *, ids=None, created_at=None):
    from modules import db

    ids = data["ids"] if ids is None else ids
    before = {(r["image_id"], r["keyword_norm"]): r for r in data["rows"]}
    current = _rows(ids)
    present = {(r["image_id"], r["keyword_norm"]) for r in current}
    scope = set(ids)
    fixed = 0
    for key, old in before.items():
        if key[0] not in scope or key[1].startswith("species:") or key in present:
            continue
        stamp = None if created_at is None else created_at.get(key)
        if stamp is None:
            db.get_connector().execute(
                "INSERT INTO image_keywords (image_id, keyword_id, source, confidence, relevance_weight) "
                "SELECT ?, keyword_id, ?, ?, ? FROM keywords_dim WHERE keyword_norm = ?",
                (old["image_id"], old["source"], old["confidence"], old["relevance_weight"], old["keyword_norm"]))
        else:
            db.get_connector().execute(
                "INSERT INTO image_keywords (image_id, keyword_id, source, confidence, relevance_weight, created_at) "
                "SELECT ?, keyword_id, ?, ?, ?, ? FROM keywords_dim WHERE keyword_norm = ?",
                (old["image_id"], old["source"], old["confidence"], old["relevance_weight"], stamp,
                 old["keyword_norm"]))
        fixed += 1
    snapshotted = set(data["ids"])
    for row in current:
        old = before.get((row["image_id"], row["keyword_norm"]))
        if row["keyword_norm"].startswith("species:"):
            continue
        if old is None:
            # A species write can also add a parent tag (e.g. ``birds``); membership stays as snapshotted.
            if row["image_id"] in snapshotted:
                db.get_connector().execute(
                    "DELETE FROM image_keywords WHERE image_id = ? "
                    "AND keyword_id = (SELECT keyword_id FROM keywords_dim WHERE keyword_norm = ?)",
                    (row["image_id"], row["keyword_norm"]))
                fixed += 1
            continue
        if any(row[k] != old[k] for k in ("source", "confidence", "relevance_weight")):
            db.get_connector().execute(
                "UPDATE image_keywords SET source = ?, confidence = ?, relevance_weight = ? WHERE image_id = ? "
                "AND keyword_id = (SELECT keyword_id FROM keywords_dim WHERE keyword_norm = ?)",
                (old["source"], old["confidence"], old["relevance_weight"], row["image_id"], row["keyword_norm"]))
            fixed += 1
    return {"restored_rows": fixed}


def verify(snap: Path, full: Path | None = None, *, ids=None):
    """Raise on prediction or metadata drift; partial verification never passes."""
    data = _read(snap)
    predictions = None
    if not data.get("preserve_species", False):
        if full is None:
            raise ValueError("frozen full predictions required")
        predictions = {int(r["image_id"]): r for r in _read(full, FULL_SHA256)["images"]}
    return _verify(data, predictions, ids=ids)


def _verify(data, predictions, *, ids=None):
    ids = data["ids"] if ids is None else ids
    if not set(ids) <= set(data["ids"]):
        raise ValueError("IDs missing from preservation snapshot")
    before = {(r["image_id"], r["keyword_norm"]): r for r in data["rows"] if r["image_id"] in ids}
    after = {(r["image_id"], r["keyword_norm"]): r for r in _rows(ids)}
    preserve = data.get("preserve_species", False)

    def filtered(rows):
        return {k: v for k, v in rows.items() if preserve or not k[1].startswith("species:")}

    if filtered(before) != filtered(after):
        raise ValueError("keyword membership or source/confidence/relevance metadata changed")
    old_images = {r["id"]: r["data"] for r in data["images"] if r["id"] in ids}
    new_images = {r["id"]: r["data"] for r in _images(ids)}
    ignored = {"bird_bbox"} if preserve else {"keywords"}

    def projected(rows):
        return {iid: {k: v for k, v in row.items() if k not in ignored} for iid, row in rows.items()}

    if projected(old_images) != projected(new_images):
        raise ValueError("preserved image metadata, captions or scores changed")
    if preserve:
        if _species_state(ids) != data["species_state"]:
            raise ValueError("small-image phase or embedding state changed")
    elif predictions is not None:
        for iid in ids:
            actual = [r for (image_id, keyword), r in after.items()
                      if image_id == iid and keyword.startswith("species:")]
            want = (predictions[iid].get("new") or "").lower()
            if sorted(r["keyword_norm"] for r in actual) != ([f"species:{want}"] if want else []):
                raise ValueError(f"species prediction differs from frozen result for image {iid}")
            if any(r["source"] != "bioclip_region" or r["confidence"] is None or r["confidence"] <= 0.5
                   for r in actual):
                raise ValueError(f"species provenance/floor mismatch for image {iid}")
    return {"verified_ids": ids, "metadata_preserved": True}


def run(ids, species_list, cohort, full, snap, completed):
    from modules import bird_species as bs
    from modules import db

    species, predictions = preflight(ids, species_list, cohort, full)
    frozen = _read(cohort, COHORT_SHA256)
    baseline = _read(snap)
    if baseline.get("preserve_species") or not set(ids) <= set(baseline["ids"]):
        raise ValueError("refresh IDs missing from refresh preservation snapshot")
    binding = {"snapshot_sha256": hashlib.sha256(snap.read_bytes()).hexdigest(), "full_sha256": FULL_SHA256}
    receipt = _read(completed) if completed.exists() else {**binding, "completed_ids": []}
    if any(receipt.get(k) != v for k, v in binding.items()):
        raise ValueError("completion receipt belongs to different frozen inputs")
    done = set(receipt["completed_ids"])
    if not done <= set(baseline["ids"]):
        raise ValueError("invalid completion receipt IDs")
    if done:
        _verify(baseline, predictions, ids=sorted(done))
    pending = [iid for iid in ids if iid not in done]
    if not pending:
        return {"completed_ids": sorted(done), "remaining": 0}
    _verify(baseline, None, ids=pending)
    before = {(r["image_id"], r["keyword_norm"]): r for r in baseline["rows"] if r["image_id"] in pending}
    if before != {(r["image_id"], r["keyword_norm"]): r for r in _rows(pending)}:
        raise ValueError("pending keyword baseline changed before refresh")
    job_id = db.create_job("BIRD_SPECIES stage5 large/medium refresh #593")
    runner = bs.BirdSpeciesRunner()
    try:
        db.update_job_status(job_id, "running")
        runner.classifier = bs.new_bioclip_classifier()
        runner.classifier.load_model()
        for iid in pending:
            if db.job_should_stop_processing(job_id):
                raise RuntimeError("species refresh paused or cancelled")
            _validate_selections([iid], frozen, predictions)
            rows = db.get_images_with_keyword(keyword="birds", resolved_image_ids=[iid])
            if len(rows) != 1 or int(rows[0]["id"]) != iid:
                raise ValueError(f"image {iid} no longer bird eligible")
            stamps = _keyword_created_at([iid])
            try:
                runner._process_bird_species_image_row(rows[0], species_list=species, threshold=0.5, top_k=1,
                    phase_code="bird_species", refresh=True, log=lambda message, *args: runner.log_history.append(message))
            finally:
                _restore(baseline, ids=[iid], created_at=stamps)
            phase = db.get_connector().query_one(
                "SELECT ips.status, ips.skip_reason FROM image_phase_status ips "
                "JOIN pipeline_phases p ON p.id = ips.phase_id WHERE ips.image_id = ? AND p.code = 'bird_species'",
                (iid,))
            if not phase or (phase["status"] != "done" and
                             not (phase["status"] == "skipped" and phase["skip_reason"] == "no_species_match")):
                raise ValueError(f"species refresh failed for image {iid}")
            _verify(baseline, predictions, ids=[iid])
            done.add(iid)
            receipt.update(completed_ids=sorted(done), job_id=job_id)
            temporary = completed.with_suffix(completed.suffix + ".tmp")
            temporary.write_text(json.dumps(receipt), encoding="utf-8")
            temporary.replace(completed)
        db.update_job_status(job_id, "completed")
    except BaseException:
        current = db.get_job(job_id) or {}
        if current.get("status") not in ("paused", "cancelled", "canceled", "cancel_requested"):
            db.update_job_status(job_id, "failed", "Stopped refresh; verify preserved state before continuing")
        raise
    return {"job_id": job_id, "completed_ids": sorted(done), "remaining": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("snapshot", "preflight", "run", "restore", "verify"))
    for name in ("ids", "out", "snap", "cohort", "full", "species-list", "completed"):
        p.add_argument(f"--{name}", type=Path)
    p.add_argument("--preserve-species", action="store_true")
    p.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    required = {"snapshot": ("ids", "out"), "preflight": ("ids", "species_list", "cohort", "full"),
                "run": ("ids", "species_list", "cohort", "full", "snap", "completed"),
                "restore": ("snap",), "verify": ("snap",)}[a.action]
    if any(getattr(a, name) is None for name in required):
        p.error(f"{a.action} requires {', '.join(required)}")
    if a.action in ("run", "restore") and not a.confirm:
        p.error(f"{a.action} writes the database; pass --confirm")
    ids = _read(a.ids) if a.ids else None
    if a.action == "snapshot":
        result = snapshot(ids, a.out, preserve_species=a.preserve_species)
    elif a.action == "preflight":
        species, _ = preflight(ids, a.species_list, a.cohort, a.full)
        result = {"eligible_ids": ids, "species_count": len(species)}
    elif a.action == "run":
        result = run(ids, a.species_list, a.cohort, a.full, a.snap, a.completed)
    elif a.action == "restore":
        result = restore(a.snap)
    else:
        result = verify(a.snap, a.full, ids=ids)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
