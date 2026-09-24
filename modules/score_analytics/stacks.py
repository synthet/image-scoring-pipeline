"""Within-stack (culling) signal analysis per score dimension (pure numpy, no DB).

A stack groups near-duplicate shots; culling picks the keepers *inside* a stack.
A dimension is a useful culling signal when it separates stack members rather
than scoring the shared scene. Per dimension we report:

* ``within_std_mean`` / ``within_range_mean`` — typical spread inside a stack
* ``within_share`` — Σ within-stack SS / total SS over stacked images (1 − η²);
  low means the model mostly scores the scene, not the frame
* ``tie_rate`` — fraction of within-stack pairs closer than ``tie_eps``
* ``top_gap_mean`` / ``top_gap_z`` — best-minus-second gap (raw / in stack std)
* ``pick_auc`` — P(score(pick) > score(non-pick)) over same-stack pairs
* ``reject_auc`` — P(score(non-reject) > score(reject)) over same-stack pairs
* ``pick_top1_rate`` — stacks with a pick where the top-scored frame is a pick
* ``best_match_rate`` — stacks where the top-scored frame is ``stacks.best_image_id``
* ``agreement`` — mean within-stack Spearman between dimensions

Caveat: when picks / best images were produced by the auto-cull policy from a
composite score, agreement with that composite is circular.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from modules.score_analytics.stats import finite_or_none

DEFAULT_MIN_STACK_SIZE = 2
DEFAULT_TIE_EPS = 0.01


def _groups(stack_ids: np.ndarray, min_size: int) -> list[tuple[int, np.ndarray]]:
    stacked = np.flatnonzero(stack_ids > 0)
    if stacked.size == 0:
        return []
    order = stacked[np.argsort(stack_ids[stacked], kind="stable")]
    ids, starts, counts = np.unique(stack_ids[order], return_index=True, return_counts=True)
    return [
        (int(sid), order[s : s + c]) for sid, s, c in zip(ids, starts, counts) if c >= min_size
    ]


def _pair_wins(hi: np.ndarray, lo: np.ndarray) -> tuple[float, int]:
    """Wins (ties = 0.5) of ``hi`` over ``lo`` across all cross pairs."""
    if hi.size == 0 or lo.size == 0:
        return 0.0, 0
    diff = hi[:, None] - lo[None, :]
    return float((diff > 0).sum() + 0.5 * (diff == 0).sum()), int(diff.size)


def _rank(x: np.ndarray) -> np.ndarray:
    """Average ranks (ties share the mean rank)."""
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(x.size, dtype=np.float64)
    ranks[order] = np.arange(x.size, dtype=np.float64)
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks)
    return (sums / counts)[inv]


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
    groups = _groups(stack_ids, min_size)
    k = len(keys)

    acc = {
        key: {
            "stacks": 0,
            "images": 0,
            "std_sum": 0.0,
            "range_sum": 0.0,
            "ss_within": 0.0,
            "vals": [],
            "tie_pairs": 0,
            "pairs": 0,
            "gap_sum": 0.0,
            "gap_z_sum": 0.0,
            "gap_z_n": 0,
            "pick_wins": 0.0,
            "pick_pairs": 0,
            "reject_wins": 0.0,
            "reject_pairs": 0,
            "pick_top1_hits": 0,
            "pick_stacks": 0,
            "best_hits": 0,
            "best_stacks": 0,
        }
        for key in keys
    }
    agree_sum = np.zeros((k, k))
    agree_n = np.zeros((k, k), dtype=np.int64)
    rows: list[dict[str, Any]] = []
    stacks_with_picks = 0

    for sid, idx in groups:
        picks = pick_status[idx]
        if (picks == 1).any():
            stacks_with_picks += 1
        best_id = best.get(sid)
        full_cols: list[int] = []
        rank_cols: list[np.ndarray] = []
        for j, key in enumerate(keys):
            vals = series[key][idx]
            ok = np.isfinite(vals)
            n = int(ok.sum())
            if n < min_size:
                continue
            x = vals[ok]
            ps = picks[ok]
            a = acc[key]
            a["stacks"] += 1
            a["images"] += n
            std = float(x.std())
            a["std_sum"] += std
            a["range_sum"] += float(x.max() - x.min())
            a["ss_within"] += float(((x - x.mean()) ** 2).sum())
            a["vals"].append(x)
            diff = np.abs(x[:, None] - x[None, :])[np.triu_indices(n, 1)]
            a["tie_pairs"] += int((diff < tie_eps).sum())
            a["pairs"] += int(diff.size)
            top = np.sort(x)[::-1]
            gap = float(top[0] - top[1])
            a["gap_sum"] += gap
            if std > 0:
                a["gap_z_sum"] += gap / std
                a["gap_z_n"] += 1

            top_pos = int(np.argmax(x))
            top_image = int(image_ids[idx][ok][top_pos])
            pw, pp = _pair_wins(x[ps == 1], x[ps != 1])
            rw, rp = _pair_wins(x[ps != -1], x[ps == -1])
            a["pick_wins"] += pw
            a["pick_pairs"] += pp
            a["reject_wins"] += rw
            a["reject_pairs"] += rp
            has_pick = bool((ps == 1).any())
            if has_pick and (ps != 1).any():
                a["pick_stacks"] += 1
                a["pick_top1_hits"] += int(ps[top_pos] == 1)
            if best_id is not None and best_id in image_ids[idx][ok]:
                a["best_stacks"] += 1
                a["best_hits"] += int(top_image == best_id)

            if n == idx.size:
                full_cols.append(j)
                rank_cols.append(_rank(x))

            if per_stack:
                rows.append(
                    {
                        "stack_id": sid,
                        "dimension": key,
                        "n": n,
                        "mean": finite_or_none(x.mean()),
                        "std": finite_or_none(std),
                        "min": finite_or_none(x.min()),
                        "max": finite_or_none(x.max()),
                        "range": finite_or_none(x.max() - x.min()),
                        "top1_image_id": top_image,
                        "top_gap": finite_or_none(gap),
                        "picks": int((ps == 1).sum()),
                        "rejects": int((ps == -1).sum()),
                        "pick_auc": finite_or_none(pw / pp) if pp else None,
                        "reject_auc": finite_or_none(rw / rp) if rp else None,
                        "top1_is_pick": bool(ps[top_pos] == 1) if has_pick else None,
                        "best_image_id": best_id,
                        "top1_is_best": (top_image == best_id) if best_id is not None else None,
                    }
                )

        if len(full_cols) >= 2 and idx.size >= 3:
            R = np.column_stack(rank_cols)
            with np.errstate(invalid="ignore", divide="ignore"):
                C = np.corrcoef(R, rowvar=False)
            for a_i, j1 in enumerate(full_cols):
                for b_i, j2 in enumerate(full_cols):
                    c = C[a_i, b_i]
                    if np.isfinite(c):
                        agree_sum[j1, j2] += c
                        agree_n[j1, j2] += 1

    models = []
    for key in keys:
        a = acc[key]
        vals = np.concatenate(a["vals"]) if a["vals"] else np.array([])
        ss_total = float(((vals - vals.mean()) ** 2).sum()) if vals.size else 0.0
        models.append(
            {
                "dimension": key,
                "stacks": a["stacks"],
                "images": a["images"],
                "within_std_mean": finite_or_none(a["std_sum"] / a["stacks"]) if a["stacks"] else None,
                "within_range_mean": finite_or_none(a["range_sum"] / a["stacks"]) if a["stacks"] else None,
                "within_share": finite_or_none(a["ss_within"] / ss_total) if ss_total > 0 else None,
                "tie_rate": finite_or_none(a["tie_pairs"] / a["pairs"]) if a["pairs"] else None,
                "top_gap_mean": finite_or_none(a["gap_sum"] / a["stacks"]) if a["stacks"] else None,
                "top_gap_z": finite_or_none(a["gap_z_sum"] / a["gap_z_n"]) if a["gap_z_n"] else None,
                "pick_auc": finite_or_none(a["pick_wins"] / a["pick_pairs"]) if a["pick_pairs"] else None,
                "pick_pairs": a["pick_pairs"],
                "reject_auc": finite_or_none(a["reject_wins"] / a["reject_pairs"]) if a["reject_pairs"] else None,
                "reject_pairs": a["reject_pairs"],
                "pick_top1_rate": finite_or_none(a["pick_top1_hits"] / a["pick_stacks"]) if a["pick_stacks"] else None,
                "pick_stacks": a["pick_stacks"],
                "best_match_rate": finite_or_none(a["best_hits"] / a["best_stacks"]) if a["best_stacks"] else None,
                "best_stacks": a["best_stacks"],
            }
        )

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
        "stacks_considered": len(groups),
        "images_in_stacks": int(sum(idx.size for _, idx in groups)),
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
