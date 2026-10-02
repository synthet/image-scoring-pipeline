"""Label-free model selection: which scoring models each scenario can drop (pure numpy, no DB).

Scenarios are the ``general`` / ``technical`` / ``aesthetic`` composites and
within-stack culling. Without independent human labels nothing here measures
accuracy; every signal is agreement, redundancy or resolution:

* ``composite_ablation`` — recompute a composite without one model (same
  percentile rescaling and weight renormalization as
  ``modules.score_normalization.compute_composites``) and measure how far the
  composite, star rating, colour label, top decile and stack best frame move
* ``stack_consensus`` — within-stack Kendall τ-b and top-1 agreement of each
  model with the leave-one-out mean rank of the other candidates
* ``redundancy_groups`` — connected components of |ρ| ≥ threshold
* ``forward_select`` — greedy smallest subset reproducing a scenario target
* ``composite_verdicts`` / ``culling_verdicts`` — prespecified keep / optional /
  omittable rules (``THRESHOLDS``)
* ``build_report`` — all of the above plus the existing profile, correlation,
  PCA and stack helpers for one ``ScoreMatrix``

Agreement with ``stacks.best_image_id`` / pick status is circular (both come
from ``score_general``) and is reported as agreement with production only.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from scipy import stats as sps

from modules.score_analytics import data, stacks
from modules.score_analytics import suitability as su
from modules.score_analytics.stats import finite_or_none

PRODUCTION_MODELS = ("liqe", "spaq", "topiq", "arniqa", "ava")
CULLING_ONLY_MODELS = ("clip_quality_v0",)
LEGACY_MODELS = data.LEGACY_MODELS
RESEARCH_PREFIXES = data.RESEARCH_PREFIXES
COMPOSITES = data.COMPOSITE_KEYS
CULLING = "culling"
SCENARIOS = (*COMPOSITES, CULLING)
# Scores are stored to 3 decimals; a tie is an identical stored value, so tie
# rates do not depend on each model's numeric range.
EXACT_TIE_EPS = 1e-6
PAIR_CAP_PER_STACK = 2000

THRESHOLDS: dict[str, float] = {
    "omit_min_spearman": 0.98,
    "omit_max_rating_change": 0.02,
    "omit_max_label_change": 0.02,
    "keep_min_output_change": 0.05,
    "keep_min_pca_loading": 0.4,
    "keep_min_pca_explained": 0.10,
    "cull_keep_max_tie_rate": 0.20,
    "cull_omit_min_tie_rate": 0.50,
    "cull_omit_min_within_rho": 0.80,
    "redundancy_rho": 0.80,
    "forward_min_gain": 0.01,
    "forward_max_models": 3,
    "top_frac": 0.10,
}
CAVEAT = "Statistical only; not validated against human judgments."
LABEL_NAMES = ("Red", "Purple", "Blue", "Green")


def role_of(key: str) -> str:
    """Report role: only ``candidate`` / ``culling_candidate`` dimensions receive verdicts."""
    if key in COMPOSITES:
        return "composite"
    if key in PRODUCTION_MODELS:
        return "candidate"
    if key in CULLING_ONLY_MODELS:
        return "culling_candidate"
    if key in LEGACY_MODELS:
        return "legacy"
    if key.startswith(RESEARCH_PREFIXES):
        return "research_family"
    return "reference"


# ---------------------------------------------------------------------------
# composites (vectorized mirror of modules.score_normalization)
# ---------------------------------------------------------------------------


def rescale(values: np.ndarray, anchor: dict[str, float]) -> np.ndarray:
    """Vectorized ``rescale_percentile`` (soft floor below p02, clamp above p98); NaN preserved."""
    x = np.asarray(values, dtype=np.float64)
    p02, p98 = float(anchor["p02"]), float(anchor["p98"])
    if p98 <= p02:
        return x.copy()
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.clip((x - p02) / (p98 - p02), 0.0, 1.0)
        soft = np.where(x >= 0, 0.15 * x / p02, 0.0) if p02 > 0 else np.zeros_like(x)
    return np.where(x <= p02, soft, out)


def composite_score(series: dict[str, np.ndarray], weights: dict[str, float], anchors: dict[str, dict]) -> np.ndarray:
    """Weighted mean of rescaled models present per image, re-normalized; NaN where none present."""
    n = next(iter(series.values())).size if series else 0
    num = np.zeros(n)
    den = np.zeros(n)
    for model, w in weights.items():
        x = series.get(model)
        if x is None:
            continue
        r = rescale(x, anchors[model]) if model in anchors else np.asarray(x, dtype=np.float64)
        ok = np.isfinite(r)
        num[ok] += w * r[ok]
        den[ok] += w
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, np.clip(num / den, 0.0, 1.0), np.nan)
    return np.round(out, 4)


def ratings(general: np.ndarray, thresholds: dict[int, float]) -> np.ndarray:
    """Vectorized ``score_to_rating``; 0 where the composite is missing."""
    s = np.clip(np.asarray(general, dtype=np.float64), 0.0, 1.0)
    fin = np.isfinite(s)
    out = np.where(fin, 1, 0).astype(np.int8)
    done = ~fin
    for rating in sorted(thresholds, reverse=True):
        with np.errstate(invalid="ignore"):
            hit = ~done & (s >= thresholds[rating])
        out[hit] = rating
        done |= hit
    return out


def labels(technical: np.ndarray, aesthetic: np.ndarray, lt: dict[str, float]) -> np.ndarray:
    """Vectorized ``determine_label`` on composite arrays; '' where either is missing."""
    t = np.asarray(technical, dtype=np.float64)
    a = np.asarray(aesthetic, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        conds = [
            t < lt["red_tech_max"],
            (a > lt["purple_aes_min"]) & (t < lt["purple_tech_max"]),
            (a > lt["blue_aes_min"]) & (t > lt["blue_tech_min"]),
            t > lt["green_tech_min"],
        ]
    out = np.select(conds, [np.full(t.shape, name) for name in LABEL_NAMES], default="Yellow")
    out[~(np.isfinite(t) & np.isfinite(a))] = ""
    return out


# ---------------------------------------------------------------------------
# stack helpers
# ---------------------------------------------------------------------------


def _groups(stack_ids: np.ndarray, mask: np.ndarray, min_size: int) -> tuple[np.ndarray, np.ndarray, int]:
    """Row indices inside stacks with ≥ ``min_size`` rows passing ``mask``, and 0..k-1 stack codes."""
    idx = np.flatnonzero(mask & (stack_ids > 0))
    if idx.size == 0:
        return idx, np.zeros(0, dtype=np.int64), 0
    _, codes, sizes = np.unique(stack_ids[idx], return_inverse=True, return_counts=True)
    idx = idx[sizes[codes] >= min_size]
    if idx.size == 0:
        return idx, np.zeros(0, dtype=np.int64), 0
    _, codes = np.unique(stack_ids[idx], return_inverse=True)
    return idx, codes, int(codes.max()) + 1


def _top_rows(x: np.ndarray, codes: np.ndarray) -> np.ndarray:
    """Position of each group's highest value, in group order."""
    order = np.lexsort((-x, codes))
    first = np.r_[True, codes[order][1:] != codes[order][:-1]]
    return order[first]


def _group_max(x: np.ndarray, codes: np.ndarray, k: int) -> np.ndarray:
    out = np.full(k, -np.inf)
    np.maximum.at(out, codes, x)
    return out


def _norm_ranks(x: np.ndarray, codes: np.ndarray, k: int) -> np.ndarray:
    """Within-group average ranks scaled to [0, 1]."""
    size = np.bincount(codes, minlength=k)[codes]
    return stacks.group_average_ranks(x, codes) / np.maximum(size - 1, 1)


def _within_pairs(codes: np.ndarray, k: int, *, cap: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All within-group pairs (row a, row b, group); groups with more than ``cap`` pairs are subsampled."""
    sizes = np.bincount(codes, minlength=k)
    order = np.argsort(codes, kind="stable")
    starts = np.r_[0, np.cumsum(sizes)[:-1]]
    rng = np.random.default_rng(seed)
    A, B, G = [], [], []
    for s in np.unique(sizes[sizes >= 2]).tolist():
        groups = np.flatnonzero(sizes == s)
        if s * (s - 1) // 2 <= cap:
            iu, ju = np.triu_indices(s, 1)
            i = np.broadcast_to(iu, (groups.size, iu.size))
            j = np.broadcast_to(ju, (groups.size, ju.size))
        else:
            i = rng.integers(0, s, size=(groups.size, cap))
            j = rng.integers(0, s - 1, size=(groups.size, cap))
            j = j + (j >= i)
        base = starts[groups][:, None]
        A.append(order[base + i].ravel())
        B.append(order[base + j].ravel())
        G.append(np.repeat(groups, i.shape[1]))
    if not A:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty, empty
    return np.concatenate(A), np.concatenate(B), np.concatenate(G)


def _tau_by_group(x: np.ndarray, y: np.ndarray, pairs: tuple[np.ndarray, np.ndarray, np.ndarray], k: int) -> np.ndarray:
    """Kendall τ-b per group over ``pairs``; NaN where either side is fully tied."""
    a, b, g = pairs
    sx = np.sign(x[a] - x[b])
    sy = np.sign(y[a] - y[b])
    num = np.bincount(g, weights=sx * sy, minlength=k)
    dx = np.bincount(g, weights=sx * sx, minlength=k)
    dy = np.bincount(g, weights=sy * sy, minlength=k)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((dx > 0) & (dy > 0), num / np.sqrt(dx * dy), np.nan)


def _prepare(series, candidates, stack_ids, *, min_size, cap, seed) -> dict[str, Any]:
    """Common-support stack rows (every candidate scored) with ranks and pairs."""
    cands = [c for c in candidates if c in series]
    n = stack_ids.size
    mask = np.all([np.isfinite(series[c]) for c in cands], axis=0) if cands else np.zeros(n, dtype=bool)
    rows, codes, k = _groups(stack_ids, mask, min_size)
    prep: dict[str, Any] = {"candidates": cands, "rows": rows, "codes": codes, "k": k}
    if k:
        prep["x"] = {c: series[c][rows] for c in cands}
        prep["ranks"] = {c: _norm_ranks(prep["x"][c], codes, k) for c in cands}
        prep["pairs"] = _within_pairs(codes, k, cap=cap, seed=seed)
    return prep


# ---------------------------------------------------------------------------
# 1. composite ablation
# ---------------------------------------------------------------------------


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    both = np.isfinite(a) & np.isfinite(b)
    if both.sum() < 3 or a[both].std() == 0 or b[both].std() == 0:
        return None
    return finite_or_none(sps.spearmanr(a[both], b[both])[0])


def _shift(full: np.ndarray, abl: np.ndarray, stack_ids: np.ndarray, min_size: int, top_frac: float) -> dict[str, Any]:
    both = np.isfinite(full) & np.isfinite(abl)
    n = int(both.sum())
    out: dict[str, Any] = {"n": n, "spearman": None, "mean_abs_shift": None, "top_overlap": None,
                           "best_frame_change": None, "stacks": 0}
    if n < 3:
        return out
    a, b = full[both], abl[both]
    out["spearman"] = _spearman(a, b)
    out["mean_abs_shift"] = float(np.abs(a - b).mean())
    k = max(1, math.ceil(top_frac * n))
    top_a = np.argpartition(-a, k - 1)[:k]
    top_b = np.argpartition(-b, k - 1)[:k]
    out["top_overlap"] = float(np.intersect1d(top_a, top_b).size / k)
    rows, codes, g = _groups(stack_ids, both, min_size)
    if g:
        fa, fb = full[rows], abl[rows]
        ta, tb = _top_rows(fa, codes), _top_rows(fb, codes)
        # A different frame that ties the original best is not a change.
        out["best_frame_change"] = float(np.mean(fa[tb] < fa[ta] - 1e-12))
        out["stacks"] = g
    return out


def _change_rate(before: np.ndarray, after: np.ndarray, missing) -> float | None:
    both = (before != missing) & (after != missing)
    return float(np.mean(before[both] != after[both])) if both.any() else None


def composite_ablation(
    series: dict[str, np.ndarray],
    weights: dict[str, dict[str, float]],
    anchors: dict[str, dict],
    rating_thresholds: dict[int, float],
    label_thresholds: dict[str, float],
    stack_ids: np.ndarray,
    *,
    min_size: int = 2,
    top_frac: float = THRESHOLDS["top_frac"],
) -> list[dict[str, Any]]:
    """Drop-one rows per (composite, model) plus ``everywhere`` (model removed from every composite).

    ``rating_change`` / ``label_change`` are 0.0 when the dropped model cannot
    affect them and ``None`` when they are affected but not computable.
    """
    comps = [c for c in COMPOSITES if weights.get(c)]
    full = {c: composite_score(series, weights[c], anchors) for c in comps}
    has_labels = "technical" in full and "aesthetic" in full
    full_rating = ratings(full["general"], rating_thresholds) if "general" in full else None
    full_label = labels(full["technical"], full["aesthetic"], label_thresholds) if has_labels else None
    models = sorted({m for c in comps for m in weights[c]} & set(series))
    rows: list[dict[str, Any]] = []
    for scope in (*comps, "everywhere"):
        for model in models:
            if scope != "everywhere" and model not in weights[scope]:
                continue
            affected = [c for c in comps if model in weights[c]] if scope == "everywhere" else [scope]
            ablated = dict(full)
            for c in affected:
                ablated[c] = composite_score(series, {m: w for m, w in weights[c].items() if m != model}, anchors)
            target = scope if scope != "everywhere" else ("general" if "general" in affected else affected[0])
            row: dict[str, Any] = {"composite": scope, "model": model, "affects": affected}
            row["weight_share"] = (
                weights[scope][model] / sum(weights[scope].values()) if scope != "everywhere" and sum(weights[scope].values()) else None
            )
            row.update(_shift(full[target], ablated[target], stack_ids, min_size, top_frac))
            if scope == "everywhere":
                sp = [_spearman(full[c], ablated[c]) for c in affected]
                row["spearman"] = min((s for s in sp if s is not None), default=None)
            if "general" not in affected:
                row["rating_change"] = 0.0
            else:
                row["rating_change"] = (
                    _change_rate(full_rating, ratings(ablated["general"], rating_thresholds), 0) if full_rating is not None else None
                )
            if not {"technical", "aesthetic"} & set(affected):
                row["label_change"] = 0.0
            elif has_labels:
                after = labels(ablated["technical"], ablated["aesthetic"], label_thresholds)
                row["label_change"] = _change_rate(full_label, after, "")
            else:
                row["label_change"] = None
            rows.append(row)
    return rows


def composite_fidelity_fn(
    series: dict[str, np.ndarray], weights: dict[str, float], anchors: dict[str, dict]
) -> Callable[[Sequence[str]], float | None]:
    """Spearman between the composite built from a model subset and the full composite."""
    full = composite_score(series, weights, anchors)

    def score(subset: Sequence[str]) -> float | None:
        return _spearman(full, composite_score(series, {m: weights[m] for m in subset}, anchors))

    return score


# ---------------------------------------------------------------------------
# 2. within-stack consensus
# ---------------------------------------------------------------------------


def stack_consensus(
    series: dict[str, np.ndarray],
    candidates: Sequence[str],
    stack_ids: np.ndarray,
    *,
    min_size: int = 2,
    bootstrap: int = su.DEFAULT_BOOTSTRAP,
    seed: int = 0,
    cap: int = PAIR_CAP_PER_STACK,
) -> dict[str, Any]:
    """Agreement of each candidate with the mean within-stack rank of the other candidates.

    Uses only images scored by every candidate (common support), stacks with
    ≥ ``min_size`` such images, each stack weighted equally; CIs resample whole
    stacks. Agreement with the other models is not accuracy.
    """
    prep = _prepare(series, candidates, stack_ids, min_size=min_size, cap=cap, seed=seed)
    k = prep["k"]
    out: dict[str, Any] = {
        "candidates": prep["candidates"],
        "stacks": k,
        "images": int(prep["rows"].size),
        "definition": "leave-one-out mean of within-stack normalized ranks of the other candidates",
        "models": {},
    }
    if k == 0 or len(prep["candidates"]) < 2:
        return out
    codes = prep["codes"]
    W = su.cluster_bootstrap_weights(codes, k, bootstrap, seed)
    for c in prep["candidates"]:
        x = prep["x"][c]
        cons = np.mean([prep["ranks"][o] for o in prep["candidates"] if o != c], axis=0)
        tau = _tau_by_group(x, cons, prep["pairs"], k)
        top = _top_rows(x, codes)
        hit = (cons[top] >= _group_max(cons, codes, k) - 1e-12).astype(np.float64)
        xmax = _group_max(x, codes, k)
        top_tied = np.bincount(codes, weights=(x >= xmax[codes] - EXACT_TIE_EPS).astype(float), minlength=k) > 1
        valid = np.isfinite(tau)
        out["models"][c] = {
            "kendall_tau_b": float(tau[valid].mean()) if valid.any() else None,
            "kendall_tau_b_ci": su._ci(su._boot_mean(W[:, valid], tau[valid])) if valid.any() else (None, None),
            "stacks_defined": int(valid.sum()),
            "top1_agreement": float(hit.mean()),
            "top1_agreement_ci": su._ci(su._boot_mean(W, hit)),
            "top_tied_rate": float(top_tied.mean()),
        }
    return out


def consensus_fidelity_fn(
    series: dict[str, np.ndarray],
    candidates: Sequence[str],
    stack_ids: np.ndarray,
    *,
    min_size: int = 2,
    seed: int = 0,
    cap: int = PAIR_CAP_PER_STACK,
) -> Callable[[Sequence[str]], float | None]:
    """Mean within-stack τ-b between a subset's mean rank and the all-candidate mean rank."""
    prep = _prepare(series, candidates, stack_ids, min_size=min_size, cap=cap, seed=seed)

    def score(subset: Sequence[str]) -> float | None:
        if not prep["k"]:
            return None
        full = np.mean([prep["ranks"][c] for c in prep["candidates"]], axis=0)
        sub = np.mean([prep["ranks"][c] for c in subset], axis=0)
        tau = _tau_by_group(sub, full, prep["pairs"], prep["k"])
        return float(np.nanmean(tau)) if np.isfinite(tau).any() else None

    return score


# ---------------------------------------------------------------------------
# 3. redundancy, forward selection, PCA
# ---------------------------------------------------------------------------


def redundancy_groups(keys: Sequence[str], r: list[list[float | None]], threshold: float) -> list[dict[str, Any]]:
    """Connected components of dimensions linked by |r| ≥ ``threshold``."""
    parent = list(range(len(keys)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    links = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            v = r[i][j]
            if v is not None and abs(v) >= threshold:
                parent[find(j)] = find(i)
                links.append({"a": keys[i], "b": keys[j], "r": v})
    members: dict[int, list[str]] = {}
    for i, key in enumerate(keys):
        members.setdefault(find(i), []).append(key)
    return [
        {"members": g, "links": [lk for lk in links if lk["a"] in g]}
        for g in members.values()
        if len(g) > 1
    ]


def forward_select(
    candidates: Sequence[str],
    score_fn: Callable[[Sequence[str]], float | None],
    *,
    max_models: int = int(THRESHOLDS["forward_max_models"]),
    min_gain: float = THRESHOLDS["forward_min_gain"],
) -> dict[str, Any]:
    """Greedy forward selection; stops when the next model adds less than ``min_gain``."""
    chosen: list[str] = []
    steps: list[dict[str, Any]] = []
    best: float | None = None
    stop = f"reached {max_models} models"
    while len(chosen) < max_models:
        trials: dict[str, float] = {}
        for m in candidates:
            if m in chosen:
                continue
            s = score_fn([*chosen, m])
            if s is not None and math.isfinite(s):
                trials[m] = float(s)
        if not trials:
            stop = "no remaining candidate can be scored"
            break
        m = max(trials, key=trials.__getitem__)
        gain = None if best is None else trials[m] - best
        if gain is not None and gain < min_gain:
            stop = f"next best ({m}) adds gain {gain:.4f} < {min_gain}"
            break
        chosen.append(m)
        best = trials[m]
        steps.append({"added": m, "models": list(chosen), "score": best, "gain": gain, "alternatives": trials})
    return {"selected": chosen, "steps": steps, "stop_reason": stop}


def pca_own_components(p: dict[str, Any], th: dict[str, float] = THRESHOLDS) -> dict[str, list[dict[str, Any]]]:
    """Per model: components beyond PC1 (the shared quality axis) it loads on strongly."""
    explained = p.get("explained") or []
    out: dict[str, list[dict[str, Any]]] = {}
    for model, load in (p.get("loadings") or {}).items():
        out[model] = [
            {"component": i + 1, "loading": load[i], "explained": explained[i]}
            for i in range(1, min(len(load), len(explained)))
            if abs(load[i]) >= th["keep_min_pca_loading"] and explained[i] >= th["keep_min_pca_explained"]
        ]
    return out


# ---------------------------------------------------------------------------
# 4. verdicts
# ---------------------------------------------------------------------------


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def composite_verdicts(
    ablation_rows: list[dict[str, Any]],
    weights: dict[str, dict[str, float]],
    pca_result: dict[str, Any],
    th: dict[str, float] = THRESHOLDS,
) -> dict[str, list[dict[str, Any]]]:
    """keep (dropping moves the composite's output, or own PCA axis) > omittable > optional."""
    own = pca_own_components(pca_result, th)
    out: dict[str, list[dict[str, Any]]] = {}
    for c in COMPOSITES:
        if not weights.get(c):
            continue
        output = "star ratings" if c == "general" else "colour labels"
        rows = []
        for r in ablation_rows:
            if r["composite"] != c or role_of(r["model"]) != "candidate":
                continue
            sp, rc, lc = r["spearman"], r["rating_change"], r["label_change"]
            change = rc if c == "general" else lc
            reasons: list[str] = []
            if change is not None and change >= th["keep_min_output_change"]:
                reasons.append(f"dropping it changes {_pct(change)} of {output}")
            for h in own.get(r["model"], []):
                reasons.append(f"carries its own principal component (PC{h['component']}, loading {h['loading']:+.2f}, "
                               f"{h['explained']:.0%} of variance)")
            if reasons:
                verdict = "keep"
            elif (
                sp is not None and sp >= th["omit_min_spearman"]
                and rc is not None and rc < th["omit_max_rating_change"]
                and lc is not None and lc < th["omit_max_label_change"]
            ):
                verdict = "omittable"
                reasons.append(f"without it the composite keeps Spearman {sp:.3f}; ratings change {_pct(rc)}, labels {_pct(lc)}")
            else:
                verdict = "optional"
                reasons.append(f"without it Spearman {'n/a' if sp is None else f'{sp:.3f}'}; ratings change {_pct(rc)}, labels {_pct(lc)}")
            rows.append({"model": r["model"], "verdict": verdict, "reasons": reasons, "weight_share": r["weight_share"],
                         "spearman": sp, "rating_change": rc, "label_change": lc,
                         "best_frame_change": r["best_frame_change"], "caveat": CAVEAT})
        out[c] = rows
    return out


def culling_verdicts(
    stack_models: list[dict[str, Any]],
    consensus: dict[str, Any],
    within_r: list[list[float | None]],
    keys: Sequence[str],
    th: dict[str, float] = THRESHOLDS,
) -> list[dict[str, Any]]:
    """keep = top-half within-stack variance share and consensus τ with few ties; redundant keeps are demoted."""
    cands = list(consensus["candidates"])
    by_dim = {m["dimension"]: m for m in stack_models}
    share = {c: by_dim.get(c, {}).get("within_share") for c in cands}
    ties = {c: by_dim.get(c, {}).get("tie_rate") for c in cands}
    tau = {c: (consensus["models"].get(c) or {}).get("kendall_tau_b") for c in cands}
    idx = {k: i for i, k in enumerate(keys)}

    def rho(a: str, b: str) -> float | None:
        return within_r[idx[a]][idx[b]] if a in idx and b in idx else None

    def median(d: dict[str, float | None]) -> float | None:
        v = [x for x in d.values() if x is not None]
        return float(np.median(v)) if v else None

    med_share, med_tau = median(share), median(tau)
    eligible = [
        c for c in cands
        if share[c] is not None and tau[c] is not None and ties[c] is not None
        and share[c] >= med_share and tau[c] >= med_tau and ties[c] < th["cull_keep_max_tie_rate"]
    ]
    verdicts: dict[str, tuple[str, list[str]]] = {}
    kept: list[str] = []

    def twin(c: str) -> tuple[str, float] | None:
        for k in kept:
            r = rho(c, k)
            if r is not None and abs(r) >= th["cull_omit_min_within_rho"]:
                return k, r
        return None

    for c in sorted(eligible, key=lambda m: -tau[m]):
        dup = twin(c)
        if dup:
            verdicts[c] = ("omittable", [f"within-stack Spearman {dup[1]:.2f} with kept {dup[0]}"])
        else:
            kept.append(c)
            verdicts[c] = ("keep", [f"within-stack share {share[c]:.2f} and consensus τ-b {tau[c]:.2f} in the top half; "
                                    f"ties {_pct(ties[c])}"])
    for c in cands:
        if c in verdicts:
            continue
        if ties[c] is None:
            verdicts[c] = ("optional", ["no stack data"])
        elif ties[c] >= th["cull_omit_min_tie_rate"]:
            verdicts[c] = ("omittable", [f"tie rate {_pct(ties[c])}: cannot separate most frames"])
        elif dup := twin(c):
            verdicts[c] = ("omittable", [f"within-stack Spearman {dup[1]:.2f} with kept {dup[0]}"])
        else:
            why = []
            if share[c] is None or med_share is None or share[c] < med_share:
                why.append("within-stack share below median")
            if tau[c] is None or med_tau is None or tau[c] < med_tau:
                why.append("consensus τ-b below median")
            if ties[c] >= th["cull_keep_max_tie_rate"]:
                why.append(f"tie rate {_pct(ties[c])}")
            verdicts[c] = ("optional", why or ["no criterion met"])
    return [
        {"model": c, "verdict": verdicts[c][0], "reasons": verdicts[c][1], "within_share": share[c],
         "tie_rate": ties[c], "consensus_tau_b": tau[c],
         "top1_agreement": (consensus["models"].get(c) or {}).get("top1_agreement"),
         "best_match_rate": by_dim.get(c, {}).get("best_match_rate"), "caveat": CAVEAT}
        for c in cands
    ]


# ---------------------------------------------------------------------------
# 5. report
# ---------------------------------------------------------------------------


def _clusters(stack_ids: np.ndarray, min_size: int) -> np.ndarray:
    c = stack_ids.copy()
    ids, counts = np.unique(c[c > 0], return_counts=True)
    c[np.isin(c, ids[counts < min_size])] = 0
    return c


def build_report(
    m: data.ScoreMatrix,
    *,
    weights: dict[str, dict[str, float]],
    anchors: dict[str, dict],
    rating_thresholds: dict[int, float],
    label_thresholds: dict[str, float],
    min_size: int = 2,
    bootstrap: int = su.DEFAULT_BOOTSTRAP,
    seed: int = 0,
    thresholds: dict[str, float] | None = None,
    data_dictionary: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    th = {**THRESHOLDS, **(thresholds or {})}
    keys = list(m.keys)
    roles = {k: role_of(k) for k in keys}
    candidates = [k for k in PRODUCTION_MODELS if k in keys]
    culling_cands = candidates + [k for k in CULLING_ONLY_MODELS if k in keys]
    clusters = _clusters(m.stack_ids, min_size)
    weights = {c: {mm: float(w) for mm, w in (weights.get(c) or {}).items()} for c in COMPOSITES if weights.get(c)}

    corr = su.correlation_suite(m.series, keys, clusters, seed=seed)
    pca_res = su.pca(m.series, candidates) if len(candidates) >= 2 else {}
    stack_res = stacks.analyze_stacks(
        m.series, keys, m.stack_ids, m.pick_status, m.image_ids, m.best_image_by_stack,
        min_size=min_size, tie_eps=EXACT_TIE_EPS,
    )
    consensus = stack_consensus(m.series, culling_cands, m.stack_ids, min_size=min_size, bootstrap=bootstrap, seed=seed)
    ablation = composite_ablation(
        m.series, weights, anchors, rating_thresholds, label_thresholds, m.stack_ids,
        min_size=min_size, top_frac=th["top_frac"],
    )
    recomputed = {c: composite_score(m.series, weights[c], anchors) for c in weights}
    forward: dict[str, Any] = {}
    for c in weights:
        members = [x for x in weights[c] if x in candidates]
        forward[c] = forward_select(members, composite_fidelity_fn(m.series, weights[c], anchors),
                                    max_models=int(th["forward_max_models"]), min_gain=th["forward_min_gain"])
        forward[c]["target"] = f"Spearman with the full {c} composite"
    forward[CULLING] = forward_select(
        culling_cands, consensus_fidelity_fn(m.series, culling_cands, m.stack_ids, min_size=min_size, seed=seed),
        max_models=int(th["forward_max_models"]), min_gain=th["forward_min_gain"],
    )
    forward[CULLING]["target"] = "mean within-stack τ-b with the all-candidate consensus rank"

    verdicts = composite_verdicts(ablation, weights, pca_res, th)
    verdicts[CULLING] = culling_verdicts(stack_res["models"], consensus, corr["within_spearman"]["r"], keys, th)

    reliability = {}
    for d in data_dictionary or []:
        if d.get("dimension") in keys and d.get("rows"):
            reliability[d["dimension"]] = {
                "rows": d["rows"], "failed_pct": 100.0 * d["failed"] / d["rows"],
                "not_loaded_pct": 100.0 * d["not_loaded"] / d["rows"], "versions": d.get("versions", []),
            }

    return {
        "scope": m.scope,
        "images": m.image_count,
        "dimensions": keys,
        "kinds": {k: m.meta[k]["kind"] for k in keys},
        "coverage_pct": {k: m.meta[k]["coverage_pct"] for k in keys},
        "roles": roles,
        "candidates": {"composites": candidates, CULLING: culling_cands},
        "thresholds": th,
        "caveat": CAVEAT,
        "weights": weights,
        "profiles": {k: su.profile(m.series[k], total=m.image_count, b=bootstrap, seed=seed) for k in keys},
        "reliability": reliability,
        "correlation": corr,
        "redundancy": {
            "threshold": th["redundancy_rho"],
            "library": redundancy_groups(keys, corr["pooled_spearman"]["r"], th["redundancy_rho"]),
            "within": redundancy_groups(keys, corr["within_spearman"]["r"], th["redundancy_rho"]),
        },
        "pca": pca_res,
        "stacks": {k: v for k, v in stack_res.items() if k != "per_stack"},
        "consensus": consensus,
        "ablation": ablation,
        "recomputed_vs_stored": {c: _spearman(recomputed[c], m.series[c]) if c in m.series else None for c in recomputed},
        "forward": forward,
        "verdicts": verdicts,
    }
