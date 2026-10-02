"""Exploratory evidence and validation-selected ensembles for frozen studies."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import stats

from modules.score_analytics import study
from modules.score_analytics.study_data import candidate_groups

BASE_MODELS = ("arniqa", "ava", "clip_quality_v0", "koniq", "liqe", "paq2piq", "spaq", "topiq")


def csv_rows(path, rows):
    if not rows:
        return
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def exploratory(snapshot, sample, out):
    """Unlabelled descriptions never become an accuracy leaderboard."""
    out = Path(out)
    images = snapshot["images"]
    keys = sorted({k for r in images for k in r["scores"]})
    values = {k: np.array([r["scores"].get(k, np.nan) if r["scores"].get(k) is not None else np.nan
                           for r in images]) for k in keys}
    index = {r["id"]: i for i, r in enumerate(images)}
    groups = candidate_groups(images)
    all_stack_count = sum(g["kind"] == "stack" for g in groups)
    # The API's vectorized stacks endpoint remains the source for the exact
    # full-corpus culling numbers. This export keeps a deterministic bounded
    # sample so a portable report does not monopolize the scoring container.
    stack_idx = [np.array([index[i] for i in g["image_ids"]]) for g in groups if g["kind"] == "stack"][:300]
    profiles = []
    for k in keys:
        v = values[k]
        finite = v[np.isfinite(v)]
        within_sd, ties = [], []
        for ids in stack_idx:
            s = v[ids]
            if np.isfinite(s).all():
                within_sd.append(float(np.std(s)))
                ties.append(int(np.sum(s == s.max()) > 1))
        profiles.append({"model": k, "n": len(finite), "coverage_pct": 100 * len(finite) / len(images),
                         "median": float(np.median(finite)) if len(finite) else None,
                         "iqr": float(np.ptp(np.quantile(finite, [.25, .75]))) if len(finite) else None,
                         "distinct": len(np.unique(finite)), "complete_stacks": len(ties),
                         "top_tie_pct": 100 * np.mean(ties) if ties else None,
                         "median_within_stack_sd": float(np.median(within_sd)) if within_sd else None})
    pairs = []
    for a, b in combinations(keys, 2):
        x, y = values[a], values[b]
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < 3 or np.std(x[valid]) == 0 or np.std(y[valid]) == 0:
            continue
        within, winner = [], []
        for ids in stack_idx:
            xx, yy = x[ids], y[ids]
            if not (np.isfinite(xx).all() and np.isfinite(yy).all()):
                continue
            ta, tb = xx == xx.max(), yy == yy.max()
            winner.append(float(np.sum(ta & tb) / (ta.sum() * tb.sum())))
            if np.std(xx) > 0 and np.std(yy) > 0:
                within.append(float(stats.spearmanr(xx, yy).statistic))
        pairs.append({"a": a, "b": b, "n": int(valid.sum()),
                      "pearson": float(stats.pearsonr(x[valid], y[valid]).statistic),
                      "spearman": float(stats.spearmanr(x[valid], y[valid]).statistic),
                      "kendall_tau_b": float(stats.kendalltau(x[valid], y[valid]).statistic),
                      "within_stack_spearman": float(np.mean(within)) if within else None,
                      "within_stack_n": len(within),
                      "winner_agreement": float(np.mean(winner)) if winner else None,
                      "winner_stacks": len(winner)})
    csv_rows(out / "profiles.csv", profiles)
    csv_rows(out / "correlations.csv", pairs)
    units = [u for u in sample["units"] if not u.get("repeat_of")]
    lines = ["# Model selection study — exploratory evidence", "",
             f"Frozen {snapshot['created_at']}. {len(images):,} images; {all_stack_count:,} multi-image stacks.", "",
             "Human accuracy rankings and omission decisions are pending the new blind reviews.", "",
             "## Coverage and within-stack discrimination", "",
             "Spread and ties describe discrimination, not correctness. Scores have different scales.", "",
             "| Signal | Images | Coverage | Complete stacks | Top ties |",
             "|---|---:|---:|---:|---:|"]
    for p in profiles:
        tie = f"{p['top_tie_pct']:.1f}%" if p["top_tie_pct"] is not None else "unknown"
        lines.append(f"| {p['model']} | {p['n']:,} | {p['coverage_pct']:.2f}% | {p['complete_stacks']:,} | {tie} |")
    lines += ["", "## Strongest model correlations", "",
              "Library statistics use pairwise-complete images. Within-stack values average defined correlations",
              f"over a deterministic first {len(stack_idx):,}-stack audit sample (of {all_stack_count:,}). Winner agreement credits random choice among tied maxima.", "",
              "| Pair | Library ρ | Within-stack ρ | Images |",
              "|---|---:|---:|---:|"]
    base_pairs = sorted([p for p in pairs if p["a"] in BASE_MODELS and p["b"] in BASE_MODELS],
                        key=lambda p: abs(p["spearman"]), reverse=True)
    for p in base_pairs[:12]:
        wr = f"{p['within_stack_spearman']:.3f}" if p["within_stack_spearman"] is not None else "unknown"
        lines.append(f"| {p['a']} / {p['b']} | {p['spearman']:.3f} | {wr} | {p['n']:,} |")
    lines += ["", "## Review sample", "", f"- Original units: {dict(Counter(u['kind'] for u in units))}",
              f"- Hidden consistency repeats: {len(sample['units']) - len(units)}",
              f"- Split units: {dict(Counter(u['split'] for u in units))}",
              f"- Independent session/overlap blocks: {len({u['block'] for u in units})}",
              "- Labels start empty; existing automatic ratings and picks are excluded.",
              "- Small subgroups and too few independent test blocks cannot support omission decisions.",
              "", "## Runtime", "", snapshot["historical_timing"],
              "Use the benchmark command for measured model costs. Missing times are unknown, never zero.",
              "", "## Interpretation", "",
              "LIQE/TOPIQ and ARNIQA/LIQE are useful ablation candidates because they share some global",
              "ranking signal, but their within-stack agreement is much lower. This is a hypothesis to test.",
              "KonIQ/PaQ2PiQ require matched coverage comparisons. Reference-culling dimensions are related",
              "outputs of one research pipeline; their joint inference costs are not additive independent models.",
              "Low correlation may reflect complementary signal or noise. Human judgments decide which."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"profiles": profiles, "correlations": pairs}


def load_reviews(sample, records, reviewer):
    units = {u["id"]: u for u in sample["units"]}
    latest = {}
    for r in records:
        if r.get("reviewer") != reviewer:
            continue
        if r.get("unit_id") not in units:
            raise ValueError("Review belongs to an unknown study unit")
        study.validate_review(units[r["unit_id"]], r)
        latest[r["unit_id"]] = r
    return latest


def development_hash(sample, reviews):
    ids = {u["id"] for u in sample["units"] if u["split"] != "test"}
    raw = json.dumps({k: v for k, v in reviews.items() if k in ids}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _rows(snapshot, sample, reviews, scenario, split, models):
    images = {r["id"]: r for r in snapshot["images"]}
    result, eligible = [], 0
    for u in sample["units"]:
        r = reviews.get(u["id"])
        if u.get("repeat_of") or u["split"] != split or not r or r["status"] != "done":
            continue
        if (scenario == "culling") != (u["kind"] != "single"):
            continue
        eligible += 1
        frames = [images[i] for i in u["image_ids"]]
        x = np.array([[f["scores"].get(m, np.nan) if f["scores"].get(m) is not None else np.nan for m in models]
                      for f in frames], float)
        if not np.isfinite(x).all():
            continue
        row = {**u, "x": x, "frames_data": frames}
        if scenario == "culling":
            labels = {f["image_id"]: f for f in r["frames"]}
            row["grades"] = np.array([labels[i]["grade"] for i in u["image_ids"]])
            row["best"] = np.array([labels[i]["best"] for i in u["image_ids"]])
        else:
            row["label"] = r["ratings"][scenario]
        result.append(row)
    return result, eligible


def _normalize(rows, anchors, columns):
    # Training empirical CDFs; no fitting on validation or test images.
    def transform(x):
        return np.column_stack([np.searchsorted(anchors[j], x[:, j], side="right") / len(anchors[j])
                                for j in columns])
    return [transform(r["x"]) for r in rows]


def _fit(train, columns, anchors, scenario, method):
    z = _normalize(train, anchors, columns)
    if method == "equal":
        return np.full(len(columns), 1 / len(columns)), 0.0
    # Fixed regularization declared before validation model/subset selection.
    if scenario == "culling":
        from modules.score_analytics.suitability import fit_pairwise_logit

        xx, yy, ww = [], [], []
        for r, x in zip(train, z):
            pairs = [(a, b) for a, b in combinations(range(len(x)), 2) if r["grades"][a] != r["grades"][b]]
            for a, b in pairs:
                xx.append(x[a] - x[b])
                yy.append(float(r["grades"][a] > r["grades"][b]))
                ww.append(r["weight"] / len(pairs))
        if not xx:
            return None
        beta = fit_pairwise_logit(np.array(xx), np.array(yy), np.array(ww), l2=1e-3)
        return beta, 0.0
    x = np.vstack([r[0] for r in z])
    y = np.array([r["label"] for r in train], float)
    w = np.array([r["weight"] for r in train], float)
    w /= w.mean()
    x = np.column_stack([np.ones(len(x)), x])
    penalty = np.diag([0.0] + [1.0] * len(columns))
    coef = np.linalg.solve(x.T @ (w[:, None] * x) + penalty, x.T @ (w * y))
    return coef[1:], float(coef[0])


def predict(rows, candidate):
    if candidate.get("baseline"):
        return [np.array([r["scores"].get(candidate["baseline"], np.nan) for r in row["frames_data"]], float)
                for row in rows]
    z = _normalize(rows, candidate["anchors"], candidate["columns"])
    return [x @ np.asarray(candidate["beta"]) + candidate["intercept"] for x in z]


def _metric_rows(rows, predictions, scenario):
    result = []
    for r, p in zip(rows, predictions):
        if not np.isfinite(p).all():
            continue
        if scenario == "culling":
            metrics = study.group_metrics(p, r["grades"], r["best"])
            if metrics:
                result.append({**r, **metrics})
        else:
            result.append({**r, "prediction": float(p[0])})
    return result


def _primary(rows, weights, scenario):
    if scenario != "culling":
        return study.weighted_rho([r["prediction"] for r in rows], [r["label"] for r in rows], weights)
    valid = np.array([r.get("top1") is not None for r in rows])
    return float(np.average([r["top1"] for r in rows if r.get("top1") is not None], weights=weights[valid])) \
        if weights[valid].sum() else None


def select_candidates(snapshot, sample, reviews, *, models=BASE_MODELS, max_size=4):
    """Select on validation only; never read test labels or compute test metrics."""
    models = list(models)
    selected, tables = {}, {}
    for scenario in ("general", "technical", "aesthetic", "culling"):
        train, _ = _rows(snapshot, sample, reviews, scenario, "train", models)
        val, eligible = _rows(snapshot, sample, reviews, scenario, "validation", models)
        if len({r["block"] for r in train}) < 5 or len({r["block"] for r in val}) < 5:
            selected[scenario] = {"pending": "Need at least 5 independently labelled blocks in both train and validation",
                                  "train_units": len(train), "validation_units": len(val)}
            continue
        fit_x = np.vstack([r["x"] for r in train])
        anchors = [np.sort(fit_x[:, i]).tolist() for i in range(len(models))]
        candidates = []
        subsets = [cols for size in range(1, min(max_size, len(models)) + 1)
                   for cols in combinations(range(len(models)), size)]
        if tuple(range(len(models))) not in subsets:
            subsets.append(tuple(range(len(models))))
        for cols in subsets:
            for method in (["equal"] if len(cols) == 1 else ["equal", "regularized"]):
                fit = _fit(train, cols, anchors, scenario, method)
                if fit is None:
                    continue
                beta, intercept = fit
                c = {"models": [models[i] for i in cols], "columns": list(cols), "method": method,
                     "anchors": anchors, "beta": beta.tolist(), "intercept": intercept}
                rows = _metric_rows(val, predict(val, c), scenario)
                score = _primary(rows, np.array([r["weight"] for r in rows]), scenario)
                if score is not None:
                    c["validation_metric"] = score
                    candidates.append(c)
        baseline = "general" if scenario == "culling" else scenario
        winners = []
        for size in [1, 2, 3, 4, len(models)]:
            cs = [c for c in candidates if len(c["models"]) == size]
            if cs:
                winner = max(cs, key=lambda c: c["validation_metric"])
                if winner not in winners:
                    winners.append(winner)
        selected[scenario] = {"candidates": winners + [{"baseline": baseline, "models": [baseline]}],
                              "validation_eligible_units": eligible, "validation_common_units": len(val)}
        tables[scenario] = [{k: c[k] for k in ("models", "method", "validation_metric")} for c in candidates]
    return {"models": models, "development_label_hash": development_hash(sample, reviews),
            "scenarios": selected, "validation_search": tables,
            "regularization": "ridge alpha=1; pairwise logistic l2=0.001; fixed before validation selection"}


def evaluate_test(snapshot, sample, reviews, selection, *, resamples=1000):
    if development_hash(sample, reviews) != selection["development_label_hash"]:
        raise ValueError("Development labels changed after selection; create a new selection before test access")
    result = {}
    for scenario, sel in selection["scenarios"].items():
        if "pending" in sel:
            result[scenario] = sel
            continue
        rows, eligible = _rows(snapshot, sample, reviews, scenario, "test", selection["models"])
        results = []
        for c in sel["candidates"]:
            measured = _metric_rows(rows, predict(rows, c), scenario)
            metric = study.bootstrap_metric(measured, lambda rr, w: _primary(rr, w, scenario), resamples=resamples)
            results.append({"models": c["models"], "method": c.get("method", "production baseline"),
                            "primary": metric, "_rows": measured})
        # Paired comparison to frozen full-model candidate; same units and bootstrap draws.
        full = next((r for r in results if len(r["models"]) == len(selection["models"])), None)
        for r in results:
            if full is not None and len(r["_rows"]) == len(full["_rows"]) and r["_rows"]:
                ref = {x["id"]: x for x in full["_rows"]}

                def delta(rr, w):
                    a = _primary(rr, w, scenario)
                    b = _primary([ref[x["id"]] for x in rr], w, scenario)
                    return a - b if a is not None and b is not None else None

                comparison = study.bootstrap_metric(r["_rows"], delta, resamples=resamples)
                r["delta_vs_full"] = comparison
                enough = r["primary"]["blocks"] >= sample["policy"]["minimum_test_blocks"]
                if scenario == "culling":
                    done = sum(1 for u in sample["units"] if u["kind"] != "single" and not u.get("repeat_of")
                               and reviews.get(u["id"], {}).get("status") == "done")
                    enough = enough and done >= sample["policy"]["minimum_done_groups"]
                margin = sample["policy"]["culling_loss_margin_top1" if scenario == "culling" else "global_loss_margin_rho"]
                r["omission_evidence"] = study.omission_decision(comparison["ci95"] if enough else None,
                                                                  margin=margin, independent=True)
                r["recommendation"] = "Review subgroup and runtime evidence before production changes"
            if scenario == "culling":
                r["secondary"] = {}
                for name in ("pairwise", "pick_reject_auc", "ndcg3", "reject_selected", "pick_selected", "kendall_tau_b"):
                    subset = [x for x in r["_rows"] if x.get(name) is not None]
                    r["secondary"][name] = study.bootstrap_metric(
                        subset, lambda rr, w, key=name: float(np.average([x[key] for x in rr], weights=w)),
                        resamples=resamples)
            del r["_rows"]
        result[scenario] = {"test_eligible_units": eligible, "test_common_units": len(rows), "results": results}
    return result


def review_progress(sample, reviews):
    original = [u for u in sample["units"] if not u.get("repeat_of")]
    return {"total": len(original), "done": sum(reviews.get(u["id"], {}).get("status") == "done" for u in original),
            "by_kind": {kind: {"total": sum(u["kind"] == kind for u in original),
                                "done": sum(u["kind"] == kind and reviews.get(u["id"], {}).get("status") == "done"
                                            for u in original)} for kind in ("single", "stack", "burst")}}
