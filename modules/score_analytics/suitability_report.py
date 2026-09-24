"""Assemble the global-vs-cluster model suitability report (Nₐ / Nᵦ).

Read-only orchestration over :mod:`suitability` (pure statistics) and
:mod:`labels` (label provenance). Clusters are ``images.stack_id`` groups with
at least ``min_size`` images; everything else is treated as standalone.

Evaluation protocol:

* clusters (and standalone images) are split deterministically by id hash into
  train / validation / **untouched test**;
* per-model metrics (no fitting) are reported on all labelled data and on test;
* the pairwise logistic model is selected with grouped CV on train+validation,
  fitted on train, temperature-calibrated on validation and scored once on test;
* the suitability map uses test-set CIs when the test split has enough
  labelled clusters, otherwise all data (flagged).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import platform
from datetime import datetime, timezone
from typing import Any

import numpy as np
import scipy

from modules.score_analytics import data, labels, suitability as su

DEFAULTS: dict[str, Any] = {
    "min_size": 2,
    "bootstrap": su.DEFAULT_BOOTSTRAP,
    "seed": 0,
    "global_min": 0.3,
    "culling_min": 0.6,
    "test_frac": 0.2,
    "val_frac": 0.2,
    "folds": 5,
    "min_test_clusters": 30,
    "top_keywords": 5,
    "top_cameras": 5,
}


def split_of(ids: np.ndarray, test_frac: float, val_frac: float) -> np.ndarray:
    """Deterministic split by id hash: 0 = train, 1 = validation, 2 = test."""
    h = ((ids.astype(np.uint64) * np.uint64(2654435761)) % np.uint64(2**32)).astype(np.float64) / 2**32
    return np.where(h < test_frac, 2, np.where(h < test_frac + val_frac, 1, 0)).astype(np.int8)


def _clusters(m: data.ScoreMatrix, min_size: int) -> np.ndarray:
    c = m.stack_ids.copy()
    ids, counts = np.unique(c[c > 0], return_counts=True)
    small = ids[counts < min_size]
    c[np.isin(c, small)] = 0
    return c


def _mask_pairs(pairs: dict[str, np.ndarray], keep: np.ndarray) -> dict[str, np.ndarray]:
    return {k: v[keep] for k, v in pairs.items()}


def _culling_block(series, keys, pairs, clusters, grades, *, b, seed) -> dict[str, Any]:
    return {k: su.culling_metrics(series[k], pairs, clusters, grades, b=b, seed=seed) for k in keys}


def _temperature(z: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    """Scalar temperature t minimizing weighted log loss of σ(t·z) (validation calibration)."""
    best_t, best = 1.0, np.inf
    for t in np.exp(np.linspace(np.log(0.1), np.log(10), 61)):
        p = np.clip(su._sigmoid(t * z), 1e-9, 1 - 1e-9)
        ll = -(w @ (y * np.log(p) + (1 - y) * np.log(1 - p))) / w.sum()
        if ll < best:
            best_t, best = float(t), ll
    return best_t


def _holdout_logit(series, keys, pairs, split_pair, *, l2: float) -> dict[str, Any]:
    a, b, gdiff, w = pairs["a"], pairs["b"], pairs["gdiff"], pairs["w"]
    if a.size == 0:
        return {"skipped": "no pairs"}
    D = np.column_stack([series[k][a] - series[k][b] for k in keys])
    ok = (gdiff != 0) & np.isfinite(D).all(axis=1)
    y = (gdiff > 0).astype(float)
    parts = {name: ok & (split_pair == code) for name, code in (("train", 0), ("validation", 1), ("test", 2))}
    if min(int(parts[p].sum()) for p in parts) < 30:
        return {"skipped": "fewer than 30 decisive pairs in a split", "pairs": {p: int(v.sum()) for p, v in parts.items()}}
    scale = D[parts["train"]].std(axis=0)
    scale[scale == 0] = 1.0
    Z = np.where(np.isfinite(D), D, 0) / scale
    beta = su.fit_pairwise_logit(Z[parts["train"]], y[parts["train"]], w[parts["train"]], l2=l2)
    zv = Z[parts["validation"]] @ beta
    t = _temperature(zv, y[parts["validation"]], w[parts["validation"]])
    zt = Z[parts["test"]] @ beta
    return {
        "pairs": {p: int(v.sum()) for p, v in parts.items()},
        "temperature": t,
        "test_uncalibrated": su._logit_eval(su._sigmoid(zt), y[parts["test"]], w[parts["test"]]),
        "test_calibrated": su._logit_eval(su._sigmoid(t * zt), y[parts["test"]], w[parts["test"]]),
        "weights_std": {k: float(v) for k, v in zip(keys, beta)},
    }


def build_report(
    m: data.ScoreMatrix,
    bundle: labels.LabelBundle,
    *,
    keyword_ids: dict[str, np.ndarray] | None = None,
    **opts: Any,
) -> dict[str, Any]:
    o = {**DEFAULTS, **opts}
    b, seed = int(o["bootstrap"]), int(o["seed"])
    keys = list(m.keys)
    kinds = {k: m.meta[k]["kind"] for k in keys}
    models = [k for k in keys if kinds[k] == "model"]
    clusters = _clusters(m, int(o["min_size"]))
    grades = bundle.culling_grades
    img_split = np.where(clusters > 0, split_of(np.abs(clusters), o["test_frac"], o["val_frac"]),
                         split_of(m.image_ids, o["test_frac"], o["val_frac"]))

    report: dict[str, Any] = {
        "scope": m.scope,
        "images": m.image_count,
        "dimensions": keys,
        "kinds": kinds,
        "clusters": {
            "definition": f"images.stack_id groups with ≥ {o['min_size']} images; others standalone",
            "count": int(np.unique(clusters[clusters > 0]).size),
            "images_in_clusters": int((clusters > 0).sum()),
            "standalone_images": int((clusters == 0).sum()),
        },
        "split": {
            "method": "deterministic id hash (Knuth multiplicative) by cluster; standalone images by image id",
            "fractions": {"train": 1 - o["test_frac"] - o["val_frac"], "validation": o["val_frac"], "test": o["test_frac"]},
            "images": {name: int((img_split == code).sum()) for name, code in (("train", 0), ("validation", 1), ("test", 2))},
        },
        "labels": bundle.audit,
    }

    # 5. statistical audit
    report["profiles"] = {k: su.profile(m.series[k], total=m.image_count, b=b, seed=seed) for k in keys}
    report["co_missingness"] = {"keys": keys, "p_missing_given_row_missing": su.co_missingness(m.series, keys)}

    # 4. variance distinction
    report["variance"] = {k: su.variance_decomposition(m.series[k], clusters, b=b, seed=seed) for k in keys}

    # 6. correlation structure
    report["correlation"] = su.correlation_suite(m.series, keys, clusters, seed=seed)
    report["pca"] = su.pca(m.series, models) if len(models) >= 2 else {}

    # 7. pairwise culling (Cⱼ)
    pairs = su.build_pairs(clusters, grades, seed=seed)
    split_pair = img_split[pairs["a"]] if pairs["a"].size else np.array([], dtype=np.int8)
    test_pairs = _mask_pairs(pairs, split_pair == 2) if pairs["a"].size else pairs
    test_grades = np.where(img_split == 2, grades, labels.UNLABELLED)
    report["culling"] = {
        "label_source": bundle.culling_source,
        "labels_independent": bundle.culling_independent,
        "grades": "pick=2, keep/neutral=1, reject=0",
        "all": _culling_block(m.series, keys, pairs, clusters, grades, b=b, seed=seed),
        "test": _culling_block(m.series, keys, test_pairs, clusters, test_grades, b=b, seed=seed),
    }
    dev_pairs = _mask_pairs(pairs, split_pair != 2) if pairs["a"].size else pairs
    report["pairwise_model"] = {
        "grouped_cv_dev": su.pairwise_logit_study(m.series, models, dev_pairs, folds=int(o["folds"]), seed=seed),
        "holdout": _holdout_logit(m.series, models, pairs, split_pair, l2=1e-3),
    }

    # global agreement (Gⱼ)
    gl = bundle.global_label
    report["global"] = {
        "label_source": bundle.global_source,
        "labels_independent": bundle.global_independent,
        "all": {k: su.global_metrics(m.series[k], gl, clusters, b=b, seed=seed) for k in keys} if bundle.global_source else {},
        "test": {
            k: su.global_metrics(np.where(img_split == 2, m.series[k], np.nan), gl, clusters, b=b, seed=seed)
            for k in keys
        }
        if bundle.global_source
        else {},
        "candidate_q_global": su.ridge_global(m.series, models, gl, clusters, folds=int(o["folds"]), seed=seed)
        if bundle.global_source and models
        else {},
    }

    # 10. suitability map
    test_clusters = max((v.get("clusters") or 0) for v in report["culling"]["test"].values()) if keys else 0
    use_test = test_clusters >= o["min_test_clusters"]
    cul = report["culling"]["test" if use_test else "all"]
    glob = report["global"]["test" if use_test else "all"]
    report["suitability"] = {
        "evaluation_set": "untouched test split" if use_test else "all labelled data (test split too small)",
        "thresholds": {
            "global": f"lower 95% CI of burst-weighted Spearman(score, global label) ≥ {o['global_min']}",
            "culling": f"lower 95% CI of macro pairwise accuracy within clusters ≥ {o['culling_min']}",
        },
        "map": su.suitability_map(
            keys,
            kinds,
            glob,
            cul,
            global_min=float(o["global_min"]),
            culling_min=float(o["culling_min"]),
            global_independent=bundle.global_independent,
            culling_independent=bundle.culling_independent,
        ),
    }

    # subgroups (stack size, keyword, camera)
    report["subgroups"] = _subgroups(m, keys, pairs, clusters, grades, bundle, keyword_ids or {}, o, b=max(50, b // 4), seed=seed)
    report["findings"] = _findings(report)
    return report


def _subgroups(m, keys, pairs, clusters, grades, bundle, keyword_ids, o, *, b, seed) -> list[dict[str, Any]]:
    if not pairs["a"].size:
        return []
    a, bb = pairs["a"], pairs["b"]
    strata: list[tuple[str, str, np.ndarray]] = []
    ids, counts = np.unique(clusters[clusters > 0], return_counts=True)
    size_of = dict(zip(ids.tolist(), counts.tolist()))
    bucket = np.array([su.size_bucket(size_of.get(int(c), 0)) for c in clusters[a]])
    for name in ("2", "3-4", "5-8", "9+"):
        strata.append(("stack_size", name, bucket == name))
    for kw, kid in list(keyword_ids.items())[: int(o["top_keywords"])]:
        tagged = np.isin(m.image_ids, kid)
        strata.append(("keyword", kw, tagged[a] & tagged[bb]))
    cams, cam_counts = np.unique(bundle.camera[bundle.camera != ""], return_counts=True)
    for cam in cams[np.argsort(-cam_counts)][: int(o["top_cameras"])]:
        strata.append(("camera", str(cam), (bundle.camera[a] == cam) & (bundle.camera[bb] == cam)))
    rows = []
    for kind, name, keep in strata:
        sub = _mask_pairs(pairs, keep)
        n_clu = int(np.unique(sub["cluster"][sub["gdiff"] != 0]).size) if sub["a"].size else 0
        row: dict[str, Any] = {"stratum": kind, "value": name, "pairs": int(sub["a"].size), "clusters": n_clu}
        if n_clu < 20:
            row["note"] = "fewer than 20 labelled clusters — not estimated"
        else:
            for k in keys:
                cm = su.culling_metrics(m.series[k], sub, clusters, np.full_like(grades, labels.UNLABELLED), b=b, seed=seed)
                row[k] = {"acc": cm.get("pairwise_accuracy_macro"), "ci": cm.get("pairwise_accuracy_macro_ci")}
        rows.append(row)
    return rows


def _findings(r: dict[str, Any]) -> list[str]:
    out: list[str] = []
    lab = r["labels"]
    if not lab.get("culling_independent"):
        out.append("Culling labels are NOT verified independent of the scores: treat Cⱼ and Nᵦ membership as provisional.")
    if not lab.get("global_independent"):
        out.append("Global labels are NOT verified independent: Gⱼ and Nₐ membership are provisional or unavailable.")
    for row in r["suitability"]["map"]:
        if row["kind"] == "composite":
            continue
        out.append(
            f"{row['dimension']}: role={row['role']}"
            + (f", G={row['G']:.3f}" if row["G"] is not None else "")
            + (f", C={row['C']:.3f}" if row["C"] is not None else "")
            + (" (provisional)" if row["provisional"] else "")
        )
    for d in r["correlation"].get("pooled_vs_within", [])[:3]:
        if abs(d["delta"]) >= 0.2 or d["sign_flip"]:
            out.append(
                f"{d['a']} × {d['b']}: pooled ρ={d['pooled']:.2f} vs within-cluster ρ={d['within']:.2f}"
                + (" — sign flip (Simpson-type)" if d["sign_flip"] else "")
            )
    hold = r["pairwise_model"].get("holdout", {})
    if "test_calibrated" in hold:
        t = hold["test_calibrated"]
        out.append(
            f"Pairwise logistic ensemble on untouched test: accuracy {t['accuracy']:.3f}, log loss {t['log_loss']:.3f}, ECE {t['ece']:.3f}."
        )
    return out


def manifest(m: data.ScoreMatrix, opts: dict[str, Any], *, git_sha: str | None = None) -> dict[str, Any]:
    """Provenance: snapshot fingerprint, query/code hashes, grouping, versions."""
    q = "".join(
        inspect.getsource(f)
        for f in (data._load_from_db, data._query_fingerprint, labels.load_label_rows, labels.load_data_dictionary)
    )
    code = "".join(inspect.getsource(mod) for mod in (su, labels, data))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_fingerprint": m.fingerprint,
        "matrix_generated_at": m.generated_at,
        "scope": m.scope,
        "query_hash": hashlib.sha1(q.encode()).hexdigest(),
        "code_hash": hashlib.sha1(code.encode()).hexdigest(),
        "git_sha": git_sha,
        "grouping": f"clusters = images.stack_id with ≥ {opts.get('min_size', DEFAULTS['min_size'])} images",
        "options": {**DEFAULTS, **opts},
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "read_only": True,
    }


def _fmt(v: Any, d: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x, d) for x in v) + "]"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{d}f}"
    return str(v)


def to_markdown(report: dict[str, Any], man: dict[str, Any] | None = None) -> str:
    """Human-readable research summary of a suitability report."""
    lab = report["labels"]
    L: list[str] = [
        "# Global vs intra-cluster model suitability (Nₐ / Nᵦ)",
        "",
        f"Scope: `{report['scope']}` · {report['images']:,} images · "
        f"{report['clusters']['count']:,} clusters ({report['clusters']['definition']}).",
        "",
        "> Guiding principle: distinguish a model that spreads out numbers from one that reliably "
        "distinguishes the photographs a human would actually select.",
        "",
        "## Findings",
        "",
        *[f"- {f}" for f in report["findings"]],
        "",
        "## Label provenance (ground-truth audit)",
        "",
        f"- Culling labels used: **{lab['culling_source']}** — independent: **{_fmt(lab['culling_independent'])}**",
        f"- Global labels used: **{lab['global_source'] or 'none'}** — independent: **{_fmt(lab['global_independent'])}**",
        "",
        "| Source | Independent | Images | Picks | Rejects | Decisive clusters | Description |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in lab["sources"].items():
        L.append(
            f"| {name} | {_fmt(s.get('independent'))} | {_fmt(s.get('images', s.get('rows')))} | {_fmt(s.get('picks'))} | "
            f"{_fmt(s.get('rejects'))} | {_fmt(s.get('decisive_clusters'))} | {s.get('description', '')} |"
        )
    L += ["", *[f"- ⚠ {n}" for n in lab.get("notes", [])], *[f"- Not measurable: {n}" for n in lab.get("not_measurable", [])], ""]

    su_ = report["suitability"]
    L += [
        "## Suitability map Uⱼ = (Gⱼ, Cⱼ)",
        "",
        f"Evaluation set: {su_['evaluation_set']}. Thresholds: {su_['thresholds']['global']}; {su_['thresholds']['culling']}.",
        "",
        "| Dimension | Kind | Gⱼ | Gⱼ 95% CI | Cⱼ | Cⱼ 95% CI | In Nₐ | In Nᵦ | Role | Caveats |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in su_["map"]:
        L.append(
            f"| {r['dimension']} | {r['kind']} | {_fmt(r['G'])} | {_fmt(r['G_ci'])} | {_fmt(r['C'])} | {_fmt(r['C_ci'])} | "
            f"{_fmt(r['in_Na'])} | {_fmt(r['in_Nb'])} | **{r['role']}**{' (provisional)' if r['provisional'] else ''} | "
            f"{'; '.join(r['caveats'])} |"
        )

    L += ["", "## Variance decomposition — Var(s) = Var(E[s|C]) + E[Var(s|C)]", "",
          "| Dimension | Within share (image-w) | CI | Within share (cluster-w) | CI | ICC(1) | Median within SD |",
          "|---|---|---|---|---|---|---|"]
    for k, v in report["variance"].items():
        L.append(
            f"| {k} | {_fmt(v.get('within_share_image_weighted'))} | {_fmt(v.get('within_share_image_weighted_ci'))} | "
            f"{_fmt(v.get('within_share_cluster_weighted'))} | {_fmt(v.get('within_share_cluster_weighted_ci'))} | "
            f"{_fmt(v.get('icc1'))} | {_fmt(v.get('median_within_sd'))} |"
        )
    L += ["", "Greater within-cluster variance is only *potential* discriminatory power — see Cⱼ for alignment with labels.", ""]

    L += ["## Within-cluster culling metrics (evaluation set)", "",
          "| Dimension | Pairwise acc (macro) | CI | Top-1 | NDCG@3 | τ-b | Score tie rate | Clusters |",
          "|---|---|---|---|---|---|---|---|"]
    cul = report["culling"]["test" if su_["evaluation_set"].startswith("untouched") else "all"]
    for k, v in cul.items():
        L.append(
            f"| {k} | {_fmt(v.get('pairwise_accuracy_macro'))} | {_fmt(v.get('pairwise_accuracy_macro_ci'))} | "
            f"{_fmt(v.get('top1_agreement'))} | {_fmt(v.get('ndcg_at_3'))} | {_fmt(v.get('kendall_tau_b_mean'))} | "
            f"{_fmt(v.get('score_tie_rate'))} | {_fmt(v.get('clusters'))} |"
        )

    pm = report["pairwise_model"]
    cv = pm.get("grouped_cv_dev", {})
    L += ["", "## Candidate cluster-relative model", "", f"`{cv.get('equation', 'P(a ≻ b) = σ(Σ βⱼ Δⱼ)')}`", ""]
    if "cv" in cv:
        L += [f"Grouped {cv['folds']}-fold CV on train+validation clusters: accuracy {_fmt(cv['cv']['accuracy'])}, "
              f"log loss {_fmt(cv['cv']['log_loss'])}, Brier {_fmt(cv['cv']['brier'])}, ECE {_fmt(cv['cv']['ece'])}.", "",
              "| Dimension | β (std) | Single-model log loss | Marginal log-loss gain (drop-one) |", "|---|---|---|---|"]
        for c in cv["coefficients"]:
            L.append(f"| {c['dimension']} | {_fmt(c['beta_std'])} | {_fmt(c['single_log_loss'])} | {_fmt(c['marginal_log_loss_gain'], 4)} |")
    hold = pm.get("holdout", {})
    if "test_calibrated" in hold:
        L += ["", f"Fit on train, temperature {hold['temperature']:.2f} fitted on validation, scored once on the untouched test split: "
              f"accuracy {_fmt(hold['test_calibrated']['accuracy'])}, log loss {_fmt(hold['test_calibrated']['log_loss'])} "
              f"(uncalibrated {_fmt(hold['test_uncalibrated']['log_loss'])}), ECE {_fmt(hold['test_calibrated']['ece'])}."]
    elif hold:
        L += ["", f"Hold-out evaluation skipped: {hold.get('skipped')}"]

    qg = report["global"].get("candidate_q_global") or {}
    if qg.get("weights_std"):
        L += ["", "## Candidate global model", "", f"`{qg['equation']}`", "",
              f"Grouped CV Spearman {_fmt(qg.get('cv_spearman'))}, MAE {_fmt(qg.get('cv_mae'))} (n = {qg['n']:,}).", "",
              "| Dimension | Weight (std) |", "|---|---|", *[f"| {k} | {_fmt(v)} |" for k, v in qg["weights_std"].items()]]

    flips = [d for d in report["correlation"].get("pooled_vs_within", []) if d["sign_flip"] or abs(d["delta"]) >= 0.2]
    if flips:
        L += ["", "## Pooled vs within-cluster correlation divergences", "", "| Pair | Pooled ρ | Within ρ | Δ | Sign flip |", "|---|---|---|---|---|"]
        L += [f"| {d['a']} × {d['b']} | {_fmt(d['pooled'])} | {_fmt(d['within'])} | {_fmt(d['delta'])} | {_fmt(d['sign_flip'])} |" for d in flips[:15]]

    if report["subgroups"]:
        L += ["", "## Subgroups (pairwise accuracy, macro)", ""]
        for s in report["subgroups"]:
            if "note" in s:
                L.append(f"- {s['stratum']}={s['value']}: {s['note']} ({s['clusters']} clusters)")
            else:
                best = sorted(((k, v["acc"]) for k, v in s.items() if isinstance(v, dict) and v.get("acc") is not None), key=lambda t: -t[1])[:3]
                L.append(f"- {s['stratum']}={s['value']} ({s['clusters']} clusters): " + ", ".join(f"{k} {a:.3f}" for k, a in best))

    L += ["", "## Protocol", "",
          f"- Split: {report['split']['method']}; images per split {report['split']['images']}.",
          "- Per-cluster pairs are weighted so each cluster contributes equally; CIs are cluster-bootstrap percentile intervals.",
          "- Global agreement weighs each image by 1/|cluster| so bursts cannot dominate.",
          "- Composites (general / technical / aesthetic) are derived from models and are never independent evidence.",
          "- Read-only: no schema changes, no writes, RAW/NEF pipeline untouched.",
          "- Pick / Keep / Reject calibration and abstention policy require an independent, human-labelled cohort; "
          "until then deletion decisions must keep existing protected-pick / low-confidence / cluster-size safeguards."]
    if man:
        L += ["", "## Manifest", "", "```json", json.dumps(man, indent=2, default=str), "```"]
    return "\n".join(L) + "\n"
