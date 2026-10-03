"""Frozen, independently labelled model selection studies (no database writes).

Sampling units retain their inclusion probabilities. Overlapping groups and
shooting sessions share a split and bootstrap block. No production pick/rating
is accepted as a human label.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from itertools import combinations

import numpy as np
from scipy import stats


def connected_components(images, groups):
    parent = {r["id"]: r["id"] for r in images}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(ids):
        ids = [i for i in ids if i in parent]
        if ids:
            for i in ids[1:]:
                a, b = find(ids[0]), find(i)
                parent[max(a, b)] = min(a, b)

    sessions = defaultdict(list)
    for row in images:
        sessions[row.get("session") or f"image:{row['id']}"].append(row["id"])
    for ids in sessions.values():
        join(ids)
    for group in groups:
        join(group["image_ids"])
    return {i: find(i) for i in parent}


def split_for(component, seed=20261001):
    h = hashlib.sha256(f"{seed}:{component}".encode()).digest()
    p = int.from_bytes(h[:8], "big") / 2**64
    return "train" if p < 0.6 else "validation" if p < 0.8 else "test"


def sample_strata(pool, count, seed):
    """SRS without replacement per stratum; deterministic square-root allocation."""
    strata = defaultdict(list)
    for row in sorted(pool, key=lambda r: str(r["id"])):
        strata[row["stratum"]].append(row)
    count = min(count, len(pool))
    if count < len(strata):
        raise ValueError("Sample size must cover every stratum; coarsen strata or increase count")
    allocation = dict.fromkeys(strata, 1)
    for _ in range(count - len(strata)):
        eligible = [k for k in sorted(strata) if allocation[k] < len(strata[k])]
        key = max(eligible, key=lambda k: math.sqrt(len(strata[k])) / (allocation[k] + 1))
        allocation[key] += 1
    rng = np.random.default_rng(seed)
    result = []
    for k in sorted(strata):
        n, total = allocation[k], len(strata[k])
        for i in rng.choice(total, size=n, replace=False):
            result.append({**strata[k][i], "inclusion_probability": n / total,
                           "weight": total / n, "stratum_population": total})
    rng.shuffle(result)
    return result


def blind_unit(unit):
    return {k: unit[k] for k in ("id", "kind", "image_ids")}


def validate_review(unit, record):
    if record.get("source") != "human_blind":
        raise ValueError("Only human_blind reviews are accepted")
    if record.get("unit_id") != unit["id"] or not str(record.get("reviewer", "")).strip():
        raise ValueError("Review needs the correct unit_id and a reviewer")
    if record.get("status") not in ("done", "uncertain", "skipped"):
        raise ValueError("Invalid review status")
    if record["status"] != "done":
        return
    if unit["kind"] == "single":
        for key in ("general", "technical", "aesthetic"):
            value = record.get("ratings", {}).get(key)
            if type(value) is not int or value not in range(1, 6):
                raise ValueError("Rate general, technical and aesthetic from 1 to 5")
        return
    frames = record.get("frames", [])
    if len(frames) != len(unit["image_ids"]) or {f.get("image_id") for f in frames} != set(unit["image_ids"]):
        raise ValueError("Grade every frame exactly once")
    for f in frames:
        if type(f.get("grade")) is not int or f["grade"] not in (0, 1, 2) or type(f.get("best")) is not bool:
            raise ValueError("Each frame needs grade 0/1/2 and boolean best")
        if f["best"] and f["grade"] != 2:
            raise ValueError("Best frames must be picks")
    if any(f["grade"] > 0 for f in frames) and not any(f["best"] for f in frames):
        raise ValueError("Choose a best frame, or reject all frames")


def group_metrics(scores, grades, best):
    s, g, best = np.asarray(scores, float), np.asarray(grades, int), np.asarray(best, bool)
    if len(s) < 2 or not np.isfinite(s).all():
        return None
    top = np.isclose(s, s.max(), rtol=0, atol=1e-9)
    pair, auc = [], []
    for a, b in combinations(range(len(s)), 2):
        if g[a] == g[b]:
            continue
        value = 0.5 if abs(s[a] - s[b]) <= 1e-9 else float((s[a] - s[b]) * (g[a] - g[b]) > 0)
        pair.append(value)
        if {g[a], g[b]} == {0, 2}:
            auc.append(value)
    # Expected DCG under random ordering of exactly tied predictions.
    order = np.argsort(-s, kind="stable")
    gain = 2.0**g - 1
    expected = gain[order].copy()
    for score in np.unique(s):
        positions = np.flatnonzero(s[order] == score)
        expected[positions] = np.mean(gain[order[positions]])
    k = min(3, len(s))
    discounts = 1 / np.log2(np.arange(k) + 2)
    ideal = np.sort(gain)[::-1][:k] @ discounts
    tau = stats.kendalltau(s, g).statistic if len(np.unique(s)) > 1 and len(np.unique(g)) > 1 else None
    return {
        "top1": float(best[top].mean()) if best.any() else None,
        "pick_selected": float((g[top] == 2).mean()),
        "reject_selected": float((g[top] == 0).mean()),
        "pairwise": float(np.mean(pair)) if pair else None,
        "pick_reject_auc": float(np.mean(auc)) if auc else None,
        "ndcg3": float(expected[:k] @ discounts / ideal) if ideal > 0 else None,
        "kendall_tau_b": float(tau) if tau is not None and np.isfinite(tau) else None,
        "top_tie": int(top.sum() > 1),
    }


def weighted_rho(x, y, w):
    x, y, w = np.asarray(x, float), np.asarray(y, float), np.asarray(w, float)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    x, y, w = x[valid], y[valid], w[valid]
    if len(x) < 3:
        return None

    def ranks(v):
        _, inv = np.unique(v, return_inverse=True)
        mass = np.bincount(inv, weights=w)
        return (np.cumsum(mass) - mass / 2)[inv]

    a, b = ranks(x), ranks(y)
    a -= np.average(a, weights=w)
    b -= np.average(b, weights=w)
    den = np.sqrt(np.sum(w * a * a) * np.sum(w * b * b))
    return float(np.sum(w * a * b) / den) if den else None


def bootstrap_metric(rows, metric, *, resamples=1000, seed=20261001):
    """Poisson block bootstrap; weights remain attached to sampled units."""
    if not rows:
        return {"value": None, "ci95": None, "units": 0, "blocks": 0}
    blocks = sorted({r["block"] for r in rows})
    idx = {b: i for i, b in enumerate(blocks)}
    codes = np.array([idx[r["block"]] for r in rows])
    weights = np.array([r["weight"] for r in rows], float)
    value = metric(rows, weights)
    samples = []
    rng = np.random.default_rng(seed)
    if len(blocks) >= 2:
        for _ in range(resamples):
            w = weights * rng.poisson(1, len(blocks))[codes]
            if w.sum():
                v = metric(rows, w)
                if v is not None and np.isfinite(v):
                    samples.append(v)
    return {"value": value, "ci95": np.quantile(samples, [0.025, 0.975]).tolist() if len(samples) >= 20 else None,
            "units": len(rows), "blocks": len(blocks),
            "effective_units": float(weights.sum()**2 / (weights @ weights)),
            "successful_resamples": len(samples)}


TIE_TOLERANCE_GRID = (0.0025, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05)


def tie_tolerance_curve(groups, grid=TIE_TOLERANCE_GRID, *, margin=0.60, min_pairs=30, min_groups=10,
                        resamples=1000, seed=20261001):
    """Calibrate ``culling.tie_tolerance`` from human-graded groups (rule v2, pre-registered in #513).

    ``groups`` items: ``{"id", "scores", "grades"}``. Pairs with different grades score
    agreement 1 when the score order matches the grade order (0.5 on an exact score
    tie). For each ε, agreement among pairs with |Δscore| <= ε gets a group-cluster
    bootstrap CI. An ε is eligible with at least ``min_pairs`` pairs from ``min_groups``
    groups and a defined CI; it qualifies when the CI upper bound is <= ``margin``
    (evidence that the score orders such pairs at most marginally better than chance).
    The recommendation is the largest qualifying ε with no failing smaller eligible ε;
    otherwise None.
    """
    pairs, equal = [], []
    for g in groups:
        s, gr = np.asarray(g["scores"], float), np.asarray(g["grades"], int)
        for a, b in combinations(range(len(s)), 2):
            d = abs(s[a] - s[b])
            if gr[a] == gr[b]:
                equal.append(d)
                continue
            agree = 0.5 if d <= 1e-9 else float((s[a] - s[b]) * (gr[a] - gr[b]) > 0)
            pairs.append({"block": g["id"], "weight": 1.0, "delta": d, "agree": agree})

    def agreement(rows, w):
        return float(np.average([r["agree"] for r in rows], weights=w))

    curve, recommended, blocked = [], None, False
    for eps in sorted(grid):
        rows = [p for p in pairs if p["delta"] <= eps + 1e-12]
        boot = bootstrap_metric(rows, agreement, resamples=resamples, seed=seed)
        upper = boot["ci95"][1] if boot["ci95"] else None
        eligible = upper is not None and len(rows) >= min_pairs and boot["blocks"] >= min_groups
        qualifies = eligible and upper is not None and upper <= margin
        curve.append({"epsilon": eps, "pairs": len(rows), "groups": boot["blocks"],
                      "agreement": boot["value"], "ci95": boot["ci95"], "eligible": eligible,
                      "qualifies": qualifies})
        if eligible and not qualifies:
            blocked = True
        elif qualifies and not blocked:
            recommended = eps
    q = np.quantile(equal, [0.25, 0.5, 0.75, 0.9]).tolist() if equal else None
    return {"rule": "v2", "margin": margin, "curve": curve, "recommended_epsilon": recommended,
            "different_grade_pairs": len(pairs), "groups": len(groups),
            "equal_grade_pairs": {"n": len(equal), "abs_delta_q25_50_75_90": q}}


def inference_cost(models, timings, dependencies):
    components = {d for m in models for d in dependencies.get(m, [m])}
    if any(timings.get(d) is None for d in components):
        return None
    return sum(timings[d] for d in components)


def omission_decision(ci, *, margin, independent):
    if not independent:
        return "needs human labels"
    if ci is None:
        return "inconclusive"
    return "eligible" if ci[0] >= -margin else "inconclusive"
