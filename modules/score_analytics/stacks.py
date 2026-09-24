"""Within-stack (culling) signal analysis per score dimension (pure numpy, no DB).

A stack groups near-duplicate shots; culling picks the keepers *inside* a stack.
A dimension is a useful culling signal when it separates stack members rather
than scoring the shared scene. Per dimension we report:

* ``within_std_mean`` / ``within_range_mean`` — typical spread inside a stack
* ``within_share`` — Σ within-stack SS / total SS over stacked images (1 − η²);
  low means the model mostly scores the scene, not the frame
* ``tie_rate`` — fraction of within-stack pairs closer than ``tie_eps`` (exclusive)
* ``top_gap_mean`` / ``top_gap_z`` — best-minus-second gap (raw / in stack std)
* ``pick_auc`` — P(score(pick) > score(non-pick)) over same-stack pairs
* ``reject_auc`` — P(score(non-reject) > score(reject)) over same-stack pairs
* ``pick_top1_rate`` — stacks with a pick where the top-scored frame is a pick
* ``best_match_rate`` — stacks where the top-scored frame is ``stacks.best_image_id``
* ``agreement`` — mean within-stack Spearman between dimensions

Everything is vectorized over stacks (sort + bincount), so libraries with tens
of thousands of stacks stay interactive.

Caveat: when picks / best images were produced by the auto-cull policy from a
composite score, agreement with that composite is circular.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from modules.score_analytics.stats import finite_or_none

DEFAULT_MIN_STACK_SIZE = 2
DEFAULT_TIE_EPS = 0.01


def group_average_ranks(values: np.ndarray, codes: np.ndarray) -> np.ndarray:
    """0-based average ranks of ``values`` within each group ``codes`` (ties share the mean rank)."""
    n = values.size
    if n == 0:
        return np.zeros(0)
    order = np.lexsort((values, codes))
    v, c = values[order], codes[order]
    new_group = np.r_[True, c[1:] != c[:-1]]
    group_start = np.maximum.accumulate(np.where(new_group, np.arange(n), 0))
    pos = np.arange(n) - group_start
    new_run = new_group | np.r_[True, v[1:] != v[:-1]]
    run_id = np.cumsum(new_run) - 1
    run_mean = np.bincount(run_id, weights=pos) / np.bincount(run_id)
    ranks = np.empty(n)
    ranks[order] = run_mean[run_id]
    return ranks


def _rank(x: np.ndarray) -> np.ndarray:
    """Average ranks of one vector (kept for callers/tests)."""
    return group_average_ranks(np.asarray(x, dtype=np.float64), np.zeros(len(x), dtype=np.int64))


def _count_below(keys_sorted: np.ndarray, query: np.ndarray, floor: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per query: (# sorted keys strictly below, # equal) restricted to keys ≥ floor."""
    lo = np.searchsorted(keys_sorted, floor, side="left")
    below = np.searchsorted(keys_sorted, query, side="left") - lo
    equal = np.searchsorted(keys_sorted, query, side="right") - np.searchsorted(keys_sorted, query, side="left")
    return below, equal


def _pair_wins_grouped(x: np.ndarray, codes: np.ndarray, hi: np.ndarray, lo: np.ndarray, span: float, k: int):
    """Per group: wins (ties 0.5) of ``hi`` members over ``lo`` members, and pair counts."""
    wins = np.zeros(k)
    if not hi.any() or not lo.any():
        return wins, np.bincount(codes[hi], minlength=k) * np.bincount(codes[lo], minlength=k)
    key = codes * span + x
    lo_keys = np.sort(key[lo])
    below, equal = _count_below(lo_keys, key[hi], codes[hi] * span)
    wins = np.bincount(codes[hi], weights=below + 0.5 * equal, minlength=k)
    pairs = np.bincount(codes[hi], minlength=k) * np.bincount(codes[lo], minlength=k)
    return wins, pairs


def _dimension_stats(
    x_all: np.ndarray,
    stack_ids: np.ndarray,
    pick_status: np.ndarray,
    image_ids: np.ndarray,
    best: dict[int, int],
    min_size: int,
    tie_eps: float,
) -> dict[str, Any] | None:
    ok = np.isfinite(x_all) & (stack_ids > 0)
    if not ok.any():
        return None
    sids_all, codes0 = np.unique(stack_ids[ok], return_inverse=True)
    sizes0 = np.bincount(codes0)
    keep = sizes0[codes0] >= min_size
    if not keep.any():
        return None
    rows = np.flatnonzero(ok)[keep]
    x = x_all[rows]
    sids, codes = np.unique(stack_ids[rows], return_inverse=True)
    k = sids.size
    n = np.bincount(codes).astype(np.float64)
    s1 = np.bincount(codes, weights=x)
    s2 = np.bincount(codes, weights=x * x)
    mean = s1 / n
    var = np.maximum(s2 / n - mean**2, 0.0)
    std = np.sqrt(var)
    mx = np.full(k, -np.inf)
    mn = np.full(k, np.inf)
    np.maximum.at(mx, codes, x)
    np.minimum.at(mn, codes, x)
    ss_within = float((var * n).sum())

    span = float(x.max() - x.min()) + 2 * tie_eps + 1.0
    key = codes * span + x
    sorted_keys = np.sort(key)
    # |Δ| < tie_eps with a 1e-9 guard: scores are stored to 3 decimals, so gaps of exactly
    # tie_eps are common and must not flip on float rounding.
    tie_pairs = int(
        (np.searchsorted(sorted_keys, sorted_keys + (tie_eps - 1e-9), side="left") - np.arange(sorted_keys.size) - 1).sum()
    )
    pairs = int((n * (n - 1) / 2).sum())

    order = np.lexsort((-x, codes))
    first = np.r_[True, codes[order][1:] != codes[order][:-1]]
    top_idx = order[first]  # row positions (into x) of each stack's top frame
    second_idx = order[np.flatnonzero(first) + 1]
    gap = x[top_idx] - x[second_idx]
    top_image = image_ids[rows][top_idx]

    ps = pick_status[rows]
    is_pick, is_rej = ps == 1, ps == -1
    pick_w, pick_p = _pair_wins_grouped(x, codes, is_pick, ~is_pick, span, k)
    rej_w, rej_p = _pair_wins_grouped(x, codes, ~is_rej, is_rej, span, k)
    n_pick = np.bincount(codes, weights=is_pick.astype(float), minlength=k)
    has_pick_and_other = (n_pick > 0) & (n_pick < n)
    top_is_pick = ps[top_idx] == 1

    best_id = np.array([best.get(int(s), -1) for s in sids])
    present = np.zeros(k, dtype=bool)
    if best:
        is_best = image_ids[rows] == best_id[codes]
        present = np.bincount(codes, weights=is_best.astype(float), minlength=k) > 0

    return {
        "sids": sids,
        "codes": codes,
        "rows": rows,
        "n": n,
        "mean": mean,
        "std": std,
        "min": mn,
        "max": mx,
        "gap": gap,
        "top_image": top_image,
        "picks": n_pick,
        "rejects": np.bincount(codes, weights=is_rej.astype(float), minlength=k),
        "pick_w": pick_w,
        "pick_p": pick_p,
        "rej_w": rej_w,
        "rej_p": rej_p,
        "has_pick_and_other": has_pick_and_other,
        "top_is_pick": top_is_pick,
        "best_id": best_id,
        "best_present": present,
        "ss_within": ss_within,
        "ss_total": float(((x - x.mean()) ** 2).sum()),
        "tie_pairs": tie_pairs,
        "pairs": pairs,
    }


def analyze_stacks(
    series: dict[str, np.ndarray],
    keys: list[str],
    stack_ids: np.ndarray,
    pick_status: np.ndarray,
    image_ids: np.ndarray,
    best_image_by_stack: dict[int, int] | None = None,
    *,
    min_size: int = DEFAULT_MIN_STACK_SIZE,
    tie_eps: float = DEFAULT_TIE_EPS,
    per_stack: bool = False,
) -> dict[str, Any]:
    """Aggregate within-stack signal metrics per dimension (optionally per-stack rows)."""
    best = best_image_by_stack or {}
    stacked = stack_ids > 0
    sid_all, sizes_all = np.unique(stack_ids[stacked], return_counts=True)
    eligible = sid_all[sizes_all >= min_size]
    in_groups = np.isin(stack_ids, eligible)
    stacks_with_picks = int(np.unique(stack_ids[in_groups & (pick_status == 1)]).size)

    models = []
    rows: list[dict[str, Any]] = []
    per_dim: dict[str, dict[str, Any] | None] = {}
    for key in keys:
        d = _dimension_stats(series[key], stack_ids, pick_status, image_ids, best, min_size, tie_eps)
        per_dim[key] = d
        if d is None:
            models.append({"dimension": key, "stacks": 0, "images": 0, "pick_pairs": 0, "reject_pairs": 0,
                           "pick_stacks": 0, "best_stacks": 0, **{f: None for f in (
                               "within_std_mean", "within_range_mean", "within_share", "tie_rate", "top_gap_mean",
                               "top_gap_z", "pick_auc", "reject_auc", "pick_top1_rate", "best_match_rate")}})
            continue
        k = d["sids"].size
        pos_std = d["std"] > 0
        pick_pairs = int(d["pick_p"].sum())
        rej_pairs = int(d["rej_p"].sum())
        pick_stacks = int(d["has_pick_and_other"].sum())
        best_stacks = int(d["best_present"].sum())
        models.append(
            {
                "dimension": key,
                "stacks": int(k),
                "images": int(d["n"].sum()),
                "within_std_mean": finite_or_none(d["std"].mean()),
                "within_range_mean": finite_or_none((d["max"] - d["min"]).mean()),
                "within_share": finite_or_none(d["ss_within"] / d["ss_total"]) if d["ss_total"] > 0 else None,
                "tie_rate": finite_or_none(d["tie_pairs"] / d["pairs"]) if d["pairs"] else None,
                "top_gap_mean": finite_or_none(d["gap"].mean()),
                "top_gap_z": finite_or_none((d["gap"][pos_std] / d["std"][pos_std]).mean()) if pos_std.any() else None,
                "pick_auc": finite_or_none(d["pick_w"].sum() / pick_pairs) if pick_pairs else None,
                "pick_pairs": pick_pairs,
                "reject_auc": finite_or_none(d["rej_w"].sum() / rej_pairs) if rej_pairs else None,
                "reject_pairs": rej_pairs,
                "pick_top1_rate": finite_or_none(d["top_is_pick"][d["has_pick_and_other"]].mean()) if pick_stacks else None,
                "pick_stacks": pick_stacks,
                "best_match_rate": finite_or_none(
                    (d["top_image"][d["best_present"]] == d["best_id"][d["best_present"]]).mean()
                )
                if best_stacks
                else None,
                "best_stacks": best_stacks,
            }
        )
        if per_stack:
            for g in range(k):
                has_pick = d["picks"][g] > 0
                bid = int(d["best_id"][g])
                rows.append(
                    {
                        "stack_id": int(d["sids"][g]),
                        "dimension": key,
                        "n": int(d["n"][g]),
                        "mean": finite_or_none(d["mean"][g]),
                        "std": finite_or_none(d["std"][g]),
                        "min": finite_or_none(d["min"][g]),
                        "max": finite_or_none(d["max"][g]),
                        "range": finite_or_none(d["max"][g] - d["min"][g]),
                        "top1_image_id": int(d["top_image"][g]),
                        "top_gap": finite_or_none(d["gap"][g]),
                        "picks": int(d["picks"][g]),
                        "rejects": int(d["rejects"][g]),
                        "pick_auc": finite_or_none(d["pick_w"][g] / d["pick_p"][g]) if d["pick_p"][g] else None,
                        "reject_auc": finite_or_none(d["rej_w"][g] / d["rej_p"][g]) if d["rej_p"][g] else None,
                        "top1_is_pick": bool(d["top_is_pick"][g]) if has_pick else None,
                        "best_image_id": bid if bid >= 0 else None,
                        "top1_is_best": bool(int(d["top_image"][g]) == bid) if bid >= 0 else None,
                    }
                )

    agree_sum, agree_n = _agreement(series, keys, stack_ids, eligible)
    ranking = sorted(
        (m for m in models if m["stacks"]),
        key=lambda m: (
            -(m["pick_auc"] if m["pick_auc"] is not None else -1),
            -(m["within_share"] or 0),
        ),
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        agree = np.where(agree_n > 0, agree_sum / np.maximum(agree_n, 1), np.nan)

    result: dict[str, Any] = {
        "min_size": min_size,
        "tie_eps": tie_eps,
        "stacks_considered": int(eligible.size),
        "images_in_stacks": int(in_groups.sum()),
        "stacks_with_picks": stacks_with_picks,
        "keys": keys,
        "models": models,
        "ranking": [m["dimension"] for m in ranking],
        "agreement": {
            "spearman": [[finite_or_none(v) for v in row] for row in agree.tolist()],
            "stacks": agree_n.tolist(),
        },
    }
    if per_stack:
        result["per_stack"] = rows
    return result


def _agreement(series, keys, stack_ids, eligible) -> tuple[np.ndarray, np.ndarray]:
    """Mean within-stack Spearman between dimensions over stacks of ≥ 3 images fully scored by both."""
    k = len(keys)
    agree_sum = np.zeros((k, k))
    agree_n = np.zeros((k, k), dtype=np.int64)
    member = np.isin(stack_ids, eligible)
    if not member.any():
        return agree_sum, agree_n
    sids, codes = np.unique(stack_ids[member], return_inverse=True)
    size = np.bincount(codes).astype(float)
    g = sids.size
    centered: list[np.ndarray | None] = []
    full: list[np.ndarray] = []
    for key in keys:
        x = series[key][member]
        fin = np.isfinite(x)
        is_full = np.bincount(codes, weights=fin.astype(float), minlength=g) == size
        use = is_full[codes] & (size[codes] >= 3)
        c = np.full(x.size, np.nan)
        if use.any():
            r = group_average_ranks(x[use], codes[use])
            c[use] = r - (size[codes[use]] - 1) / 2
        centered.append(c)
        full.append(is_full & (size >= 3))
    for i in range(k):
        for j in range(i, k):
            both = full[i] & full[j]
            if not both.any():
                continue
            m = both[codes]
            ci, cj, cc = centered[i][m], centered[j][m], codes[m]
            sxy = np.bincount(cc, weights=ci * cj, minlength=g)[both]
            sxx = np.bincount(cc, weights=ci * ci, minlength=g)[both]
            syy = np.bincount(cc, weights=cj * cj, minlength=g)[both]
            valid = (sxx > 0) & (syy > 0)
            if not valid.any():
                continue
            rho = sxy[valid] / np.sqrt(sxx[valid] * syy[valid])
            agree_sum[i, j] = agree_sum[j, i] = rho.sum()
            agree_n[i, j] = agree_n[j, i] = int(valid.sum())
    return agree_sum, agree_n
