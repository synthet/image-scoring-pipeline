"""Shadow species re-run for images with a promoted localization selection (#493).

The 4,401 images promoted under ``v1_regate_rule/3`` (#472) previously had
``bird_bbox = {"detected": false}``, so ``bird_species`` labelled them without a bird crop
(full frame, or the embedded detector's box). They now have a validated region. This asks
whether a crop of that *selected* region changes the answer:

* how often the top-1 species changes;
* whether top-1 confidence rises;
* whether images that abstained (no label above ``--threshold``) now get one, and vice versa.

Reuses ``BioCLIPClassifier.classify(region=...)``, the production stage-5 crop path, with the
selection's region (``species_input_for_image`` would read the current run, which for these
images is the v1 shadow box, not the selected one).

Read-only against production: no keywords, ``bird_bbox`` or phase status are written.
Writes ``<out>.json`` (per image) and ``<out>.md`` (summary).

Usage (gpu-shell container, project root)::

    python -m scripts.research.bird_crop.species_selection_shadow --limit 20
    python -m scripts.research.bird_crop.species_selection_shadow \\
        --selected-by "v1_regate_rule/3:a1c2e1f64b24cc79" --out reports/bird-crop/species_selection_shadow
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import Counter
from pathlib import Path
from statistics import mean, median

logger = logging.getLogger("bird_crop.species_selection_shadow")

DEFAULT_RULE = "v1_regate_rule/3:a1c2e1f64b24cc79"
SPECIES_PREFIX = "species:"

_SQL_SELECTED = """
SELECT i.id, i.file_path, g.x1, g.y1, g.x2, g.y2
FROM image_localization_selections s
JOIN images i ON i.id = s.image_id
JOIN image_regions g ON g.id = s.region_id AND g.localization_run_id = s.localization_run_id
WHERE s.selected_by = ? AND s.detector_key = 'bird' AND s.revoked_at IS NULL
ORDER BY i.id
"""

_SQL_SPECIES = """
SELECT ik.image_id, kd.keyword_norm, ik.confidence, ik.source
FROM image_keywords ik
JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
WHERE ik.image_id = ? AND kd.keyword_norm LIKE 'species:%'
ORDER BY (ik.source LIKE 'bioclip%') DESC, ik.confidence DESC NULLS LAST
"""

#: Sources whose ``confidence`` is a BioCLIP probability. ``auto`` and
#: ``repair_legacy_keywords_junction`` rows carry a placeholder 1.0.
_MODEL_SOURCES = ("bioclip", "bioclip_region")


def compare(old: dict | None, preds: list[tuple[str, float]], threshold: float) -> dict:
    """One image's outcome.

    ``old`` is the stored primary species keyword (``{"species", "confidence", "source", "all"}``,
    ``confidence`` ``None`` unless it is a model probability; ``all`` every stored species) or
    ``None`` when the image has none. ``preds`` is the new ranking, unthresholded, best first.
    """
    new_top = preds[0] if preds else None
    new_label = new_top[0].lower() if new_top and new_top[1] >= threshold else None
    old_label = old["species"] if old else None
    if old_label is None and new_label is None:
        outcome = "both_abstain"
    elif old_label is None:
        outcome = "now_labelled"
    elif new_label is None:
        outcome = "now_abstains"
    elif old_label == new_label:
        outcome = "same"
    else:
        outcome = "changed"
    old_conf = old.get("confidence") if old else None
    new_conf = new_top[1] if new_top else None
    return {
        "outcome": outcome,
        "old": old_label, "old_conf": old_conf, "old_source": old.get("source") if old else None,
        "new": new_label, "new_top": new_top[0].lower() if new_top else None, "new_conf": new_conf,
        "new_top3": [[n.lower(), p] for n, p in preds[:3]],
        "conf_delta": (new_conf - old_conf) if outcome == "same" and old_conf is not None else None,
        "new_in_old_set": outcome == "changed" and new_label in (old.get("all") or []),
    }


def summarise(results: list[dict]) -> dict:
    """Counts by outcome, plus confidence deltas where the label did not change."""
    outcomes = Counter(r["outcome"] for r in results)
    deltas = [r["conf_delta"] for r in results if r.get("conf_delta") is not None]
    labelled = [r for r in results if r["outcome"] in ("same", "changed")]
    return {
        "n": len(results),
        "outcomes": dict(outcomes),
        "changed_rate": round(outcomes["changed"] / len(labelled), 4) if labelled else None,
        "changed_but_in_old_set": sum(bool(r.get("new_in_old_set")) for r in results),
        "same_label_conf_delta": {
            "n": len(deltas),
            "mean": round(mean(deltas), 4) if deltas else None,
            "median": round(median(deltas), 4) if deltas else None,
            "rose": sum(d > 0 for d in deltas),
        },
        "changed_conf": {
            "old_mean": _mean_of(r["old_conf"] for r in results if r["outcome"] == "changed"),
            "new_mean": _mean_of(r["new_conf"] for r in results
                                 if r["outcome"] == "changed" and r["old_conf"] is not None),
        },
        "old_sources": dict(Counter(r["old_source"] for r in results if r["old_source"])),
    }


def _mean_of(values) -> float | None:
    vals = [v for v in values if v is not None]
    return round(mean(vals), 4) if vals else None


def render_markdown(meta: dict, summary: dict) -> str:
    lines = [
        "# Species shadow re-run on promoted selections (#493)\n",
        f"- rule: `{meta['selected_by']}`; threshold {meta['threshold']}; {meta['elapsed_s']:.0f}s",
        f"- images classified: {summary['n']} (skipped: {meta['skipped']})",
        "",
        "| outcome | n |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in sorted(summary["outcomes"].items(), key=lambda kv: -kv[1])]
    d = summary["same_label_conf_delta"]
    c = summary["changed_conf"]
    lines += [
        "",
        f"- top-1 changed on {summary['changed_rate']} of images labelled both times "
        f"({summary['changed_but_in_old_set']} of those picked another stored species)",
        f"- same label (BioCLIP-confidence rows only): confidence delta mean {d['mean']}, median {d['median']}, rose on {d['rose']}/{d['n']}",
        f"- changed label: mean confidence {c['old_mean']} -> {c['new_mean']}",
        f"- stored label sources: {summary['old_sources']}",
    ]
    return "\n".join(lines) + "\n"


def _old_species(conn, image_id: int) -> dict | None:
    rows = conn.query(_SQL_SPECIES, (image_id,))
    if not rows:
        return None
    names = [r["keyword_norm"][len(SPECIES_PREFIX):].strip().lower() for r in rows]
    top = rows[0]
    model_conf = top.get("source") in _MODEL_SOURCES
    return {"species": names[0], "confidence": top.get("confidence") if model_conf else None,
            "source": top.get("source"), "all": names}


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--selected-by", default=DEFAULT_RULE)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--threshold", type=float, default=0.1, help="production default for bird_species")
    ap.add_argument("--out", default="reports/bird-crop/species_selection_shadow")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from modules import db
    from modules.bird_species import BioCLIPClassifier, _load_default_species

    conn = db.get_connector()
    rows = conn.query(_SQL_SELECTED, (a.selected_by,))
    if a.limit > 0:
        rows = rows[: a.limit]
    species = _load_default_species()
    clf = BioCLIPClassifier()
    logger.info("candidates: %d, species list: %d", len(rows), len(species))

    results, skipped, t0 = [], Counter(), time.time()
    for n, row in enumerate(rows, 1):
        if n % 200 == 0:
            logger.info("%d/%d %.0fs %s", n, len(rows), time.time() - t0, dict(Counter(r["outcome"] for r in results)))
        path = row.get("file_path") or ""
        if not path or not os.path.exists(path):
            skipped["file_missing"] += 1
            continue
        region = (float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"]))
        preds = clf.classify(path, species, threshold=0.0, top_k=3, region=region, use_detector=False)
        if not preds:
            skipped["classify_error"] += 1
            continue
        results.append({"image_id": int(row["id"]), **compare(_old_species(conn, int(row["id"])), preds, a.threshold)})

    meta = {"selected_by": a.selected_by, "threshold": a.threshold, "elapsed_s": time.time() - t0,
            "skipped": dict(skipped)}
    summary = summarise(results)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps({"meta": meta, "summary": summary, "images": results}, indent=1),
                                        encoding="utf-8")
    out.with_suffix(".md").write_text(render_markdown(meta, summary), encoding="utf-8")
    logger.info("summary: %s", json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
