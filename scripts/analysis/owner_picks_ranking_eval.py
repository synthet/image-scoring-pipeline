#!/usr/bin/env python3
"""Owner-pick within-stack ranking evaluation (#739).

Implements docs/planning/owner-picks-ranking-preregistration.md including revision R1. Read-only:
reads the DB and the EXIF of exported JPEGs; writes only the JSON report given by --out.

Labels:
  primary   exported JPEG whose camera frame stem (e.g. DSC_1234) AND capture second match a RAW frame
  secondary primary plus exports matched by capture second alone, admitted only when exactly one DB
            frame has that capture second (R1); reported separately, never decides adoption
Model: pairwise logistic regression (no intercept, L2) on within-stack z-scored feature differences.
Evaluation: leave one capture year out (years with < 30 eligible stacks merged into a neighbour);
top-1 (primary), pairwise accuracy and NDCG@3 (secondary) against four baselines; stack bootstrap CIs.

Run in gpu-shell (CPU only):
  python scripts/analysis/owner_picks_ranking_eval.py --exports /mnt/d/Photos/Export --out <report.json>
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
from collections import Counter, defaultdict

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from modules import db
from modules.selection import (
    DEFAULT_DEDICATED_RANK_WEIGHTS,
    _clip_quality_cfg,
    blended_rank_value,
    dedicated_rank_value,
)

QUALITY = ("liqe", "spaq", "topiq", "arniqa", "ava")
CLIP = "clip_quality_v0"
BASE_FEATURES = (*QUALITY, CLIP, "eye_conf", "eye_visible", "af_in_box", "af_known")
GROUP_OF = {**{f: "quality" for f in QUALITY}, CLIP: "clip", "eye_conf": "eye", "eye_visible": "eye",
            "af_in_box": "af", "af_known": "af"}
STEM = re.compile(r"([A-Z]{3}_\d{4})", re.I)
PAIR_CAP = 20
SEED = "owner-picks-739"
MIN_FOLD_STACKS = 30
C_GRID = (0.01, 0.1, 1.0, 10.0)
BOOTSTRAP = 2000


# --------------------------------------------------------------------------- labels

def export_keys(root: str) -> tuple[set, Counter, int]:
    """(stem, second) set for stem-named exports, Counter of export seconds, unreadable count."""
    stem_keys, seconds, unreadable = set(), Counter(), 0
    for base, _dirs, files in os.walk(root):
        for name in files:
            if not name.lower().endswith((".jpg", ".jpeg")):
                continue
            try:
                exif = Image.open(os.path.join(base, name)).getexif()
                value = exif.get_ifd(0x8769).get(36867) or exif.get(306)
            except Exception:
                value = None
            if not value:
                unreadable += 1
                continue
            sec = str(value)[:19].replace(":", "-", 2)
            seconds[sec] += 1
            m = STEM.search(name)
            if m:
                stem_keys.add((m.group(1).upper(), sec))
    return stem_keys, seconds, unreadable


# --------------------------------------------------------------------------- data

def load_frames() -> list[dict]:
    rows = db.get_connector().query(
        "SELECT i.id, i.file_name, i.stack_id, i.sub_stack_id, i.score_general, i.bird_bbox, "
        "e.date_time_original, e.orientation, e.af_metadata "
        "FROM images i LEFT JOIN image_exif e ON e.image_id = i.id WHERE i.stack_id IS NOT NULL"
    )
    for r in rows:
        dto = r.get("date_time_original")
        r["second"] = str(dto)[:19] if dto else None
        r["year"] = r["second"][:4] if r["second"] else "unknown"
    return rows


def load_model_scores(ids: set[int]) -> dict[int, dict]:
    names = (*QUALITY, CLIP)
    rows = db.get_connector().query(
        "SELECT image_id, model_name, normalized, status FROM image_model_scores "
        "WHERE model_name IN (" + ",".join("?" * len(names)) + ") AND NOT COALESCE(is_shadow, FALSE)",
        names,
    )
    out: dict[int, dict] = defaultdict(dict)
    for r in rows:
        if r["image_id"] in ids:
            out[r["image_id"]][r["model_name"]] = {"normalized": r["normalized"], "status": r["status"]}
    return out


def load_eye(ids: set[int]) -> dict[int, tuple[float, int]]:
    rows = db.get_connector().query(
        "SELECT lr.image_id, k.confidence, k.visible FROM image_region_keypoints k "
        "JOIN image_keypoint_runs kr ON kr.id = k.keypoint_run_id AND kr.is_current "
        "JOIN image_regions g ON g.id = kr.region_id AND g.rank = 0 "
        "JOIN image_localization_runs lr ON lr.id = g.localization_run_id AND lr.is_current "
        "WHERE k.name IN ('left_eye', 'right_eye')"
    )
    out: dict[int, tuple[float, int]] = {}
    for r in rows:
        if r["image_id"] not in ids:
            continue
        conf, vis = out.get(r["image_id"], (0.0, 0))
        out[r["image_id"]] = (max(conf, float(r["confidence"] or 0.0)), max(vis, int(bool(r["visible"]))))
    return out


def af_in_box(frame: dict) -> float | None:
    """1/0 when the AF centre is inside / outside the bird box, None when unknown.

    Rotated frames (orientation != 1) are unknown: the AF box is in sensor coordinates.
    """
    af, box = frame.get("af_metadata"), frame.get("bird_bbox")
    if isinstance(af, str):
        af = json.loads(af)
    if isinstance(box, str):
        box = json.loads(box)
    if not af or not box or not isinstance(af.get("box"), dict) or "x1" not in box:
        return None
    if frame.get("orientation") not in (None, 1):
        return None
    w, h = box.get("img_w"), box.get("img_h")
    if not w or not h:
        return None
    cx, cy = af["box"].get("center_x"), af["box"].get("center_y")
    if cx is None or cy is None:
        return None
    return float(box["x1"] / w <= cx <= box["x2"] / w and box["y1"] / h <= cy <= box["y2"] / h)


# --------------------------------------------------------------------------- features

def raw_features(frame, scores, eye) -> dict[str, float | None]:
    s = scores.get(frame["id"], {})
    feat = {}
    for name in (*QUALITY, CLIP):
        e = s.get(name) or {}
        feat[name] = float(e["normalized"]) if e.get("status") == "success" and e.get("normalized") is not None else None
    conf, vis = eye.get(frame["id"], (None, None))
    feat["eye_conf"], feat["eye_visible"] = conf, (float(vis) if vis is not None else None)
    af = af_in_box(frame)
    feat["af_in_box"], feat["af_known"] = (af if af is not None else None), float(af is not None)
    return feat


def stack_matrix(members, feats, columns):
    """Within-stack z-scored matrix; missing values -> stack median plus missing_<f> flag columns."""
    raw = np.array([[np.nan if feats[m][c] is None else feats[m][c] for c in BASE_FEATURES] for m in members], float)
    cols = []
    for j, name in enumerate(BASE_FEATURES):
        col = raw[:, j].copy()
        miss = np.isnan(col)
        med = np.nanmedian(col) if (~miss).any() else 0.0
        col[miss] = med
        cols.append(col)
        if f"missing_{name}" in columns:
            cols.append(miss.astype(float))
    m = np.column_stack(cols)
    sd = m.std(axis=0)
    return np.where(sd > 0, (m - m.mean(axis=0)) / np.where(sd > 0, sd, 1), 0.0)


# --------------------------------------------------------------------------- evaluation

def expected_top1(scores, labels) -> float:
    best = max(scores)
    tied = [lab for sc, lab in zip(scores, labels) if sc == best]
    return sum(tied) / len(tied)


def pair_acc(scores, labels, pairs) -> list[float]:
    return [1.0 if scores[p] > scores[n] else 0.5 if scores[p] == scores[n] else 0.0 for p, n in pairs]


def ndcg3(scores, labels) -> float:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])[:3]
    dcg = sum(labels[i] / math.log2(r + 2) for r, i in enumerate(order))
    ideal = sum(1 / math.log2(r + 2) for r in range(min(3, sum(labels))))
    return dcg / ideal if ideal else 0.0


def folds_from(stacks_by_year: dict[str, int]) -> list[list[str]]:
    """Years in order; a year with < MIN_FOLD_STACKS stacks is merged forward (last fold absorbs the rest)."""
    folds, buf, n = [], [], 0
    for year in sorted(stacks_by_year):
        buf.append(year)
        n += stacks_by_year[year]
        if n >= MIN_FOLD_STACKS:
            folds.append(buf)
            buf, n = [], 0
    if buf:
        if folds:
            folds[-1].extend(buf)
        else:
            folds.append(buf)
    return folds


def run_tier(name, groups, labels, feats, scores, frames_by_id, clip_w):
    eligible = {}
    for key, members in groups.items():
        lab = [int(m in labels) for m in members]
        if 0 < sum(lab) < len(lab):
            eligible[key] = (members, lab)
    if not eligible:
        return {"tier": name, "eligible_stacks": 0}

    columns = list(BASE_FEATURES)
    all_members = [m for members, _ in eligible.values() for m in members]
    for f in BASE_FEATURES:
        if any(feats[m][f] is None for m in all_members):
            columns.append(f"missing_{f}")
    ordered_cols = []
    for f in BASE_FEATURES:
        ordered_cols.append(f)
        if f"missing_{f}" in columns:
            ordered_cols.append(f"missing_{f}")

    stack_year, mats, pairs = {}, {}, {}
    for key, (members, lab) in eligible.items():
        years = Counter(frames_by_id[m]["year"] for m in members)
        stack_year[key] = years.most_common(1)[0][0]
        mats[key] = stack_matrix(members, feats, ordered_cols)
        combos = [(i, j) for i, a in enumerate(lab) if a for j, b in enumerate(lab) if not b]
        random.Random(f"{SEED}|{key}").shuffle(combos)
        pairs[key] = combos[:PAIR_CAP]

    folds = folds_from(Counter(stack_year.values()))

    def xy(keys):
        xs, ys, gs = [], [], []
        for k in keys:
            for i, j in pairs[k]:
                d = mats[k][i] - mats[k][j]
                xs += [d, -d]
                ys += [1, 0]
                gs += [str(k), str(k)]
        return np.array(xs), np.array(ys), np.array(gs)

    def fit(keys):
        x, y, g = xy(keys)
        n_groups = len(set(g))
        best_c, best = C_GRID[0], -1.0
        if n_groups >= 4:
            for c in C_GRID:
                accs = []
                for tr, te in GroupKFold(n_splits=min(5, n_groups)).split(x, y, g):
                    mdl = LogisticRegression(C=c, fit_intercept=False, max_iter=2000).fit(x[tr], y[tr])
                    accs.append(mdl.score(x[te], y[te]))
                if np.mean(accs) > best:
                    best, best_c = float(np.mean(accs)), c
        return LogisticRegression(C=best_c, fit_intercept=False, max_iter=2000).fit(x, y), best_c

    def method_scores(key, model):
        members, _ = eligible[key]
        frames = [frames_by_id[m] for m in members]
        sg = [float(f.get("score_general") or 0) for f in frames]
        ded = [dedicated_rank_value(scores.get(m, {}), DEFAULT_DEDICATED_RANK_WEIGHTS) for m in members]
        ded = [d if d is not None else s for d, s in zip(ded, sg)]
        clip_vals = [(scores.get(m, {}).get(CLIP) or {}).get("normalized") for m in members]
        blend = [blended_rank_value({"score_general": s, CLIP: c}, "score_general", clip_w) for s, c in zip(sg, clip_vals)]
        learned = list(mats[key] @ model.coef_[0])
        return {"learned": learned, "score_general": sg, "dedicated_rank": ded, "clip_blend": blend}

    per_stack = []  # (fold_index, key, {method: (top1, ndcg)}, {method: [pair accs]})
    fold_report = []
    for fi, test_years in enumerate(folds):
        test = [k for k in eligible if stack_year[k] in test_years]
        train = [k for k in eligible if stack_year[k] not in test_years]
        if not train or not test:
            continue
        model, c = fit(train)
        for k in test:
            _, lab = eligible[k]
            ms = method_scores(k, model)
            row = {m: (expected_top1(v, lab), ndcg3(v, lab)) for m, v in ms.items()}
            row["random"] = (sum(lab) / len(lab), None)
            accs = {m: pair_acc(v, lab, pairs[k]) for m, v in ms.items()}
            per_stack.append((fi, k, row, accs))
        fold_report.append({"test_years": test_years, "train_stacks": len(train), "test_stacks": len(test), "C": c})

    methods = ("learned", "score_general", "dedicated_rank", "clip_blend", "random")
    rng = random.Random(SEED)

    def pooled(method, rows):
        return float(np.mean([r[2][method][0] for r in rows]))

    summary = {}
    for m in methods:
        boot = sorted(pooled(m, [rng.choice(per_stack) for _ in per_stack]) for _ in range(BOOTSTRAP))
        summary[m] = {
            "top1": round(pooled(m, per_stack), 4),
            "top1_95ci": [round(boot[int(0.025 * BOOTSTRAP)], 4), round(boot[int(0.975 * BOOTSTRAP) - 1], 4)],
        }
        if m != "random":
            summary[m]["pairwise_acc"] = round(float(np.mean([a for r in per_stack for a in r[3][m]])), 4)
            summary[m]["ndcg3"] = round(float(np.mean([r[2][m][1] for r in per_stack])), 4)

    by_fold = []
    for fi, fr in enumerate(fold_report):
        rows = [r for r in per_stack if r[0] == fi]
        by_fold.append({**fr, **{m: round(pooled(m, rows), 4) for m in methods}})

    final, final_c = fit(list(eligible))
    w = dict(zip(ordered_cols, final.coef_[0].tolist()))
    mass = Counter()
    for col, val in w.items():
        mass[GROUP_OF[col.removeprefix("missing_")]] += abs(val)
    total = sum(mass.values()) or 1.0
    group_share = {g: round(v / total, 4) for g, v in mass.items()}

    baselines = ("score_general", "dedicated_rank", "clip_blend", "random")
    best = max(baselines, key=lambda b: summary[b]["top1"])
    rule1 = summary["learned"]["top1_95ci"][0] > summary[best]["top1_95ci"][1]
    wins = sum(1 for f in by_fold if f["learned"] >= f[best])
    rule2 = wins >= math.ceil(2 * len(by_fold) / 3) if by_fold else False
    rule3 = max(group_share.values()) <= 0.8

    return {
        "tier": name,
        "eligible_stacks": len(eligible),
        "pairs": sum(len(p) for p in pairs.values()),
        "stacks_by_year": dict(sorted(Counter(stack_year.values()).items())),
        "folds": by_fold,
        "summary": summary,
        "best_baseline": best,
        "final_model": {"C": final_c, "weights": {k: round(v, 4) for k, v in w.items()}, "group_weight_share": group_share},
        "adoption_rule": {"ci_separation": rule1, "years_won": f"{wins}/{len(by_fold)}", "years_rule": rule2,
                          "no_dominant_group": rule3, "adopt": bool(rule1 and rule2 and rule3)},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exports", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    stem_keys, export_seconds, unreadable = export_keys(args.exports)
    frames = load_frames()
    frames_by_id = {f["id"]: f for f in frames}
    ids = set(frames_by_id)
    second_counts = Counter(f["second"] for f in frames if f["second"])

    primary, secondary_extra = set(), set()
    for f in frames:
        m = STEM.search(f["file_name"] or "")
        if m and f["second"] and (m.group(1).upper(), f["second"]) in stem_keys:
            primary.add(f["id"])
    for f in frames:
        sec = f["second"]
        if f["id"] not in primary and sec and export_seconds.get(sec) and second_counts[sec] == 1:
            secondary_extra.add(f["id"])

    groups = defaultdict(list)
    for f in frames:
        groups[(f["stack_id"], f.get("sub_stack_id"))].append(f["id"])

    scores = load_model_scores(ids)
    eye = load_eye(ids)
    feats = {i: raw_features(frames_by_id[i], scores, eye) for i in ids}
    clip_w = float(_clip_quality_cfg()["weight"])

    report = {
        "preregistration": "docs/planning/owner-picks-ranking-preregistration.md (incl. R1)",
        "labels": {"export_jpegs_unreadable_exif": unreadable, "primary_frames": len(primary),
                   "secondary_extra_frames": len(secondary_extra)},
        "excluded_feature_groups": {"focus": "noise-corrected sharpness is not stored in the DB; excluded per the frozen rule"},
        "af_in_box_note": "unknown for rotated frames (orientation != 1) and frames without AF metadata or a bird box",
        "clip_blend_weight": clip_w,
        "primary": run_tier("primary", groups, primary, feats, scores, frames_by_id, clip_w),
        "secondary": run_tier("secondary", groups, primary | secondary_extra, feats, scores, frames_by_id, clip_w),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, default=str)
    print(json.dumps({t: report[t].get("adoption_rule") for t in ("primary", "secondary")}, indent=1))


if __name__ == "__main__":
    main()
