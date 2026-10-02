#!/usr/bin/env python3
"""Label-free model selection report — which scoring models each scenario can drop (read-only).

Rates every scoring model on distribution health, redundancy (library and
within-stack correlation, PCA), unique contribution to the ``general`` /
``technical`` / ``aesthetic`` composites (drop-one ablation), within-stack
separation and consensus agreement, plus an estimated cost table. Writes
keep / optional / omittable verdicts per scenario with the smallest model set
that reproduces each scenario target.

Without independent human labels every number is agreement or resolution, not
accuracy; the report says so on every verdict.

Nothing is written to the database. Run in gpu-shell (see AGENTS.md)::

    python scripts/analysis/model_selection_report.py
    python scripts/analysis/model_selection_report.py --bootstrap 500 --out reports/model_selection/full
    python scripts/analysis/model_selection_report.py --keyword bird
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import logging
import platform
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import numpy as np

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules import score_normalization as sn  # noqa: E402
from modules.score_analytics import data, labels  # noqa: E402
from modules.score_analytics import model_selection as ms  # noqa: E402
from modules.score_analytics.io import Writer  # noqa: E402

logger = logging.getLogger("model_selection_report")

# Estimated, not measured: architecture facts from modules/engines/* and the
# published model designs; relative cost is an order-of-magnitude guess.
COST_TABLE = [
    {"model": "liqe", "runtime": "PyTorch (pyiqa)", "architecture": "CLIP ViT-B/32 image tower + cached text prompts",
     "params_approx": "~88M (image tower)", "input": "224 px crops", "shared_backbone": "none in production",
     "relative_cost": "medium"},
    {"model": "topiq", "runtime": "PyTorch (pyiqa)", "architecture": "TOPIQ-NR, ResNet-50 multi-scale features",
     "params_approx": "~45M", "input": "full image (resized)", "shared_backbone": "none", "relative_cost": "medium"},
    {"model": "arniqa", "runtime": "PyTorch (pyiqa)", "architecture": "ARNIQA, ResNet-50 encoder + linear regressor at 2 scales",
     "params_approx": "~24M", "input": "full + half resolution", "shared_backbone": "none", "relative_cost": "medium"},
    {"model": "spaq", "runtime": "TensorFlow (MUSIQ)", "architecture": "MUSIQ multi-scale transformer, SPAQ checkpoint",
     "params_approx": "~27M", "input": "multi-scale patches of the full image", "shared_backbone": "TF session shared with ava",
     "relative_cost": "high"},
    {"model": "ava", "runtime": "TensorFlow (MUSIQ)", "architecture": "MUSIQ multi-scale transformer, AVA checkpoint",
     "params_approx": "~27M", "input": "multi-scale patches of the full image", "shared_backbone": "TF session shared with spaq",
     "relative_cost": "high"},
    {"model": "clip_quality_v0", "runtime": "PyTorch (CLIP text tower)", "architecture": "prompt similarity on stored clip_vit_b32_image embeddings",
     "params_approx": "text tower only", "input": "existing 512-d embedding", "shared_backbone": "keywords-phase CLIP embedding",
     "relative_cost": "near zero when the embedding exists"},
]

PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948", "#b07aa1", "#9c755f"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def _fmt(v: Any, d: int = 3) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (float, np.floating)):
        return f"{float(v):.{d}f}"
    return str(v)


def _pct(v: Any, d: int = 1) -> str:
    return "—" if v is None else f"{100 * float(v):.{d}f}%"


def _ci(v: Any, d: int = 3) -> str:
    if isinstance(v, (list, tuple)) and len(v) == 2 and v[0] is not None:
        return f"[{v[0]:.{d}f}, {v[1]:.{d}f}]"
    return "—"


def observed_timings(limit: int) -> dict[str, Any]:
    """Median per-model inference time from legacy ``images.scores_json`` blobs, when that column exists."""
    if not labels._column_exists("images", "scores_json"):
        return {"available": False, "note": "images.scores_json is not present; per-model timings are not persisted"}
    rows = data._select(
        "SELECT scores_json FROM images WHERE scores_json IS NOT NULL ORDER BY id DESC LIMIT %s", (int(limit),)
    )
    times: dict[str, list[float]] = defaultdict(list)
    for (raw,) in rows:
        try:
            blob = raw if isinstance(raw, dict) else json.loads(raw)
        except (TypeError, ValueError):
            continue
        for name, r in ((blob or {}).get("models") or {}).items():
            t = r.get("inference_time_seconds") if isinstance(r, dict) else None
            if isinstance(t, (int, float)) and t >= 0:
                times[name].append(float(t))
    return {
        "available": bool(times),
        "rows_sampled": len(rows),
        "models": {
            n: {"n": len(v), "median_s": float(np.median(v)), "p95_s": float(np.percentile(v, 95))}
            for n, v in sorted(times.items())
        },
    }


def manifest(m: data.ScoreMatrix, opts: dict[str, Any]) -> dict[str, Any]:
    q = "".join(inspect.getsource(f) for f in (data._load_from_db, data._query_fingerprint))
    import scipy

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_fingerprint": m.fingerprint,
        "matrix_generated_at": m.generated_at,
        "scope": m.scope,
        "query_hash": hashlib.sha1(q.encode()).hexdigest(),
        "code_hash": hashlib.sha1(inspect.getsource(ms).encode()).hexdigest(),
        "git_sha": _git_sha(),
        "grouping": f"stacks = images.stack_id with ≥ {opts['min_size']} images",
        "options": opts,
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "read_only": True,
    }


# ---------------------------------------------------------------------------
# SVG charts (no plotting dependency)
# ---------------------------------------------------------------------------


def _svg(width: int, height: int, body: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="12">'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>' + "".join(body) + "</svg>"
    )


def _text(x: float, y: float, s: str, *, anchor: str = "start", size: int = 12, weight: str = "normal", fill: str = "#222") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}">{escape(s)}</text>')


def bar_chart(title: str, categories: list[str], series: dict[str, list[float | None]], *, xmax: float | None = None,
              pct: bool = False, note: str = "") -> str:
    """Horizontal grouped bars: one group per category, one bar per series."""
    names = list(series)
    bar_h, gap, left, right, top = 12, 10, 150, 90, 50
    group_h = bar_h * len(names) + gap
    height = top + group_h * len(categories) + 40 + 18 * len(names)
    width = 760
    vals = [v for s in series.values() for v in s if v is not None]
    hi = xmax if xmax is not None else (max(vals) if vals else 1.0) or 1.0
    lo = min(0.0, min(vals)) if vals else 0.0
    span = (hi - lo) or 1.0
    plot_w = width - left - right

    def px(v: float) -> float:
        return left + (v - lo) / span * plot_w

    body = [_text(10, 22, title, size=15, weight="bold")]
    if note:
        body.append(_text(10, 40, note, size=11, fill="#666"))
    zero = px(0.0)
    body.append(f'<line x1="{zero:.1f}" y1="{top - 4}" x2="{zero:.1f}" y2="{top + group_h * len(categories)}" stroke="#999"/>')
    for gi, cat in enumerate(categories):
        y0 = top + gi * group_h
        body.append(_text(left - 8, y0 + group_h / 2 + 2, cat, anchor="end"))
        for si, name in enumerate(names):
            v = series[name][gi]
            y = y0 + si * bar_h
            if v is None:
                body.append(_text(zero + 4, y + bar_h - 2, "n/a", size=10, fill="#999"))
                continue
            x1, x2 = sorted((zero, px(v)))
            body.append(f'<rect x="{x1:.1f}" y="{y:.1f}" width="{max(x2 - x1, 0.5):.1f}" height="{bar_h - 2}" '
                        f'fill="{PALETTE[si % len(PALETTE)]}"/>')
            label = f"{100 * v:.1f}%" if pct else f"{v:.3f}"
            body.append(_text(max(x2, zero) + 4, y + bar_h - 3, label, size=10))
    ly = top + group_h * len(categories) + 20
    for si, name in enumerate(names):
        body.append(f'<rect x="{left}" y="{ly + si * 18 - 9}" width="10" height="10" fill="{PALETTE[si % len(PALETTE)]}"/>')
        body.append(_text(left + 16, ly + si * 18, name, size=11))
    return _svg(width, int(height), body)


def _diverging(v: float | None) -> str:
    if v is None:
        return "#eeeeee"
    v = max(-1.0, min(1.0, float(v)))
    if v >= 0:
        r, g, b = 255, int(255 * (1 - v * 0.75)), int(255 * (1 - v * 0.85))
    else:
        r, g, b = int(255 * (1 + v * 0.85)), int(255 * (1 + v * 0.6)), 255
    return f"rgb({r},{g},{b})"


def heatmaps(title: str, keys: list[str], panels: list[tuple[str, list[list[float | None]]]]) -> str:
    cell, label_w, top = 30, 140, 150
    panel_w = label_w + cell * len(keys) + 30
    width = panel_w * len(panels) + 10
    height = top + cell * len(keys) + 30
    body = [_text(10, 22, title, size=15, weight="bold"),
            _text(10, 40, "Spearman ρ; red = positive, blue = negative, grey = not computable", size=11, fill="#666")]
    for pi, (sub, mat) in enumerate(panels):
        ox = pi * panel_w + 10
        body.append(_text(ox + label_w, 62, sub, size=13, weight="bold"))
        for j, k in enumerate(keys):
            x = ox + label_w + j * cell + cell / 2
            body.append(f'<text x="{x:.1f}" y="{top - 6}" font-size="10" transform="rotate(-60 {x:.1f} {top - 6})">{escape(k)}</text>')
        for i, ki in enumerate(keys):
            y = top + i * cell
            body.append(_text(ox + label_w - 6, y + cell / 2 + 4, ki, anchor="end", size=10))
            for j in range(len(keys)):
                v = mat[i][j]
                x = ox + label_w + j * cell
                body.append(f'<rect x="{x}" y="{y}" width="{cell - 1}" height="{cell - 1}" fill="{_diverging(v)}"/>')
                if v is not None:
                    body.append(_text(x + cell / 2, y + cell / 2 + 3, f"{v:.2f}", anchor="middle", size=8))
    return _svg(int(width), int(height), body)


def hist_grid(title: str, hists: dict[str, tuple[np.ndarray, np.ndarray]]) -> str:
    cols, cw, ch, pad, top = 4, 220, 120, 16, 40
    names = list(hists)
    rows = (len(names) + cols - 1) // cols
    width, height = cols * (cw + pad) + pad, top + rows * (ch + 40) + 10
    body = [_text(10, 24, title, size=15, weight="bold")]
    for n, name in enumerate(names):
        counts, edges = hists[name]
        ox = pad + (n % cols) * (cw + pad)
        oy = top + (n // cols) * (ch + 40)
        body.append(_text(ox, oy + 12, name, size=11, weight="bold"))
        body.append(f'<rect x="{ox}" y="{oy + 18}" width="{cw}" height="{ch}" fill="none" stroke="#ccc"/>')
        peak = counts.max() if counts.size and counts.max() > 0 else 1
        bw = cw / max(counts.size, 1)
        for i, c in enumerate(counts):
            h = (ch - 4) * c / peak
            body.append(f'<rect x="{ox + i * bw:.1f}" y="{oy + 18 + ch - h:.1f}" width="{max(bw - 0.5, 0.5):.1f}" '
                        f'height="{h:.1f}" fill="{PALETTE[0]}"/>')
        body.append(_text(ox, oy + ch + 32, f"{edges[0]:.2f}", size=9, fill="#666"))
        body.append(_text(ox + cw, oy + ch + 32, f"{edges[-1]:.2f}", anchor="end", size=9, fill="#666"))
    return _svg(int(width), int(height), body)


def loading_plot(title: str, pca: dict[str, Any]) -> str:
    size, mid = 460, 250
    expl = pca.get("explained") or [0, 0]
    body = [_text(10, 22, title, size=15, weight="bold"),
            _text(10, 40, f"PC1 {expl[0]:.0%} of variance (x), PC2 {expl[1] if len(expl) > 1 else 0:.0%} (y)", size=11, fill="#666")]
    body.append(f'<circle cx="{mid}" cy="{mid + 20}" r="{size / 2 - 40}" fill="none" stroke="#ddd"/>')
    body.append(f'<line x1="{mid - size / 2 + 40}" y1="{mid + 20}" x2="{mid + size / 2 - 40}" y2="{mid + 20}" stroke="#bbb"/>')
    body.append(f'<line x1="{mid}" y1="{60}" x2="{mid}" y2="{mid + size / 2 - 20}" stroke="#bbb"/>')
    r = size / 2 - 40
    for i, (name, load) in enumerate((pca.get("loadings") or {}).items()):
        if len(load) < 2:
            continue
        x, y = mid + load[0] * r, mid + 20 - load[1] * r
        color = PALETTE[i % len(PALETTE)]
        body.append(f'<line x1="{mid}" y1="{mid + 20}" x2="{x:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="2"/>')
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
        body.append(_text(x + 5, y - 4, name, size=11, fill=color))
    return _svg(size + 40, size + 60, body)


def write_charts(report: dict[str, Any], m: data.ScoreMatrix, out: Path) -> list[str]:
    charts = out / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    hists = {}
    for k in report["dimensions"]:
        v = m.series[k][np.isfinite(m.series[k])]
        if v.size:
            hists[k] = np.histogram(v, bins=40, range=(float(v.min()), float(v.max()) or 1.0))
    files["distributions.svg"] = hist_grid("Score distributions (stored values)", hists)

    corr = report["correlation"]
    keys = corr["keys"]
    files["correlation_heatmaps.svg"] = heatmaps(
        "Library vs within-stack correlation", keys,
        [("Library (pooled)", corr["pooled_spearman"]["r"]), ("Within stack (rank-centred)", corr["within_spearman"]["r"])],
    )
    if report["pca"].get("loadings"):
        files["pca_loadings.svg"] = loading_plot("PCA loadings of production models", report["pca"])

    for c in [*report["weights"], "everywhere"]:
        rows = [r for r in report["ablation"] if r["composite"] == c]
        if not rows:
            continue
        cats = [r["model"] for r in rows]
        files[f"ablation_{c}.svg"] = bar_chart(
            f"Drop-one effect on {c if c != 'everywhere' else 'all composites (model removed everywhere)'}",
            cats,
            {
                "1 − Spearman vs full": [None if r["spearman"] is None else 1 - r["spearman"] for r in rows],
                "star ratings changed": [r["rating_change"] for r in rows],
                "colour labels changed": [r["label_change"] for r in rows],
                "stack best frame changed": [r["best_frame_change"] for r in rows],
            },
            pct=True,
            note="Larger bar = the model matters more to this composite",
        )

    cull = report["verdicts"]["culling"]
    if cull:
        files["stack_signals.svg"] = bar_chart(
            "Within-stack signal (culling candidates)",
            [r["model"] for r in cull],
            {
                "within-stack variance share": [r["within_share"] for r in cull],
                "consensus Kendall τ-b": [r["consensus_tau_b"] for r in cull],
                "top-1 agreement with consensus": [r["top1_agreement"] for r in cull],
                "tie rate (identical values)": [r["tie_rate"] for r in cull],
            },
            xmax=1.0,
            note="Agreement with the other models, not accuracy",
        )
    for name, svg in files.items():
        (charts / name).write_text(svg, encoding="utf-8")
    return [f"charts/{n}" for n in files]


# ---------------------------------------------------------------------------
# REPORT.md
# ---------------------------------------------------------------------------


def to_markdown(report: dict[str, Any], man: dict[str, Any], costs: dict[str, Any], charts: list[str]) -> str:
    st = report["stacks"]
    cons = report["consensus"]
    L: list[str] = [
        "# Model selection report (label-free)",
        "",
        f"Scope: `{report['scope']}` · {report['images']:,} images · {st['stacks_considered']:,} stacks "
        f"({st['images_in_stacks']:,} images, ≥ {st['min_size']} per stack). Snapshot `{man['snapshot_fingerprint']}`, "
        f"git `{(man['git_sha'] or 'unknown')[:10]}`, generated {man['generated_at']}.",
        "",
        f"> **{report['caveat']}** No independent human labels were used. Every number below measures agreement "
        "between models, redundancy or resolution. When models disagree inside a stack, this report cannot say "
        "which one is right. `stacks.best_image_id` and pick status are derived from `score_general`, so agreement "
        "with them is agreement with current production, not accuracy.",
        "",
        "## Recommended model sets",
        "",
        "Greedy forward selection: add the model that best reproduces the scenario target; stop when the next "
        f"model adds less than {report['thresholds']['forward_min_gain']} (max {int(report['thresholds']['forward_max_models'])}).",
        "",
        "| Scenario | Target | 1 model | 2 models | 3 models | Stop reason |",
        "|---|---|---|---|---|---|",
    ]
    for sc in ms.SCENARIOS:
        f = report["forward"].get(sc)
        if not f:
            continue
        cells = []
        for i in range(3):
            if i < len(f["steps"]):
                s = f["steps"][i]
                cells.append(f"{' + '.join(s['models'])} ({s['score']:.3f})")
            else:
                cells.append("—")
        L.append(f"| {sc} | {f['target']} | {' | '.join(cells)} | {f['stop_reason']} |")

    L += ["", "## Verdicts", ""]
    for sc in ms.SCENARIOS:
        rows = report["verdicts"].get(sc)
        if not rows:
            continue
        L += [f"### {sc}", "", "| Model | Verdict | Reasons |", "|---|---|---|"]
        for r in rows:
            L.append(f"| {r['model']} | **{r['verdict']}** | {'; '.join(r['reasons'])} |")
        L.append("")

    L += [
        "## Composite drop-one ablation",
        "",
        "Composite recomputed without one model, using the configured `scoring.fusion` weights and percentile "
        "anchors (weights re-normalized over the remaining models). `everywhere` removes the model from every composite.",
        "",
        "| Composite | Model | Weight share | Spearman vs full | Mean abs shift | Ratings changed | Labels changed | "
        "Top-10% overlap | Stack best frame changed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["ablation"]:
        L.append(
            f"| {r['composite']} | {r['model']} | {_pct(r['weight_share'])} | {_fmt(r['spearman'], 4)} | "
            f"{_fmt(r['mean_abs_shift'], 4)} | {_pct(r['rating_change'])} | {_pct(r['label_change'])} | "
            f"{_pct(r['top_overlap'])} | {_pct(r['best_frame_change'])} |"
        )
    rvs = report["recomputed_vs_stored"]
    L += ["", "Recomputed (current weights) vs stored composite Spearman: "
          + ", ".join(f"{c} {_fmt(v, 4)}" for c, v in rvs.items())
          + ". Values well below 1 mean stored composites predate the current weights or anchors.", ""]

    by_dim = {x["dimension"]: x for x in st["models"]}
    L += [
        "## Within-stack (culling) signal",
        "",
        f"Consensus = leave-one-out mean within-stack rank of the other culling candidates, on {cons['stacks']:,} stacks "
        f"({cons['images']:,} images) where every candidate is scored. Ties = identical stored values.",
        "",
        "| Dimension | Role | Within-stack variance share | Tie rate | Top-gap z | Consensus τ-b [95% CI] | "
        "Top-1 agreement | Top tied | Matches production best frame |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k in report["dimensions"]:
        s = by_dim.get(k) or {}
        c = cons["models"].get(k) or {}
        tau = f"{_fmt(c.get('kendall_tau_b'))} {_ci(c.get('kendall_tau_b_ci'))}" if c else "—"
        L.append(
            f"| {k} | {report['roles'][k]} | {_fmt(s.get('within_share'))} | {_pct(s.get('tie_rate'))} | "
            f"{_fmt(s.get('top_gap_z'))} | {tau} | {_pct(c.get('top1_agreement'))} | {_pct(c.get('top_tied_rate'))} | "
            f"{_pct(s.get('best_match_rate'))} |"
        )

    red = report["redundancy"]
    L += ["", f"## Redundancy (|ρ| ≥ {red['threshold']})", ""]
    for scope, title in (("library", "Library (pooled Spearman)"), ("within", "Within stack (rank-centred Spearman)")):
        groups = red[scope]
        L.append(f"- **{title}:** " + ("; ".join(
            "{" + ", ".join(g["members"]) + "} (" + ", ".join(f"{lk['a']}–{lk['b']} {lk['r']:.2f}" for lk in g["links"]) + ")"
            for g in groups) or "no groups"))
    L += ["", "Largest library vs within-stack differences:", "", "| Pair | Library ρ | Within-stack ρ | Δ | Sign flip |",
          "|---|---|---|---|---|"]
    for d in report["correlation"]["pooled_vs_within"][:12]:
        L.append(f"| {d['a']} – {d['b']} | {d['pooled']:.3f} | {d['within']:.3f} | {d['delta']:+.3f} | {_fmt(d['sign_flip'])} |")

    p = report["pca"]
    if p.get("explained"):
        L += ["", f"## PCA of production models (n = {p['n']:,} complete rows)", "",
              "| Model | " + " | ".join(f"PC{i + 1} ({e:.0%})" for i, e in enumerate(p["explained"][:4])) + " |",
              "|---|" + "---|" * min(4, len(p["explained"]))]
        for k, load in p["loadings"].items():
            L.append(f"| {k} | " + " | ".join(f"{v:+.2f}" for v in load) + " |")

    L += ["", "## Distribution health", "",
          "| Dimension | Role | Coverage | Floor | Ceiling | Distinct-value tie fraction | On 2-decimal grid | Entropy | Failed | Not loaded |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k in report["dimensions"]:
        pr = report["profiles"][k]
        rel = report["reliability"].get(k, {})
        L.append(
            f"| {k} | {report['roles'][k]} | {report['coverage_pct'][k]:.2f}% | {_fmt(pr.get('floor_pct'), 2)}% | "
            f"{_fmt(pr.get('ceiling_pct'), 2)}% | {_fmt(pr.get('tie_fraction'))} | {_fmt(pr.get('two_decimal_grid_pct'), 1)}% | "
            f"{_fmt(pr.get('entropy_norm'))} | {_fmt(rel.get('failed_pct'), 2)}% | {_fmt(rel.get('not_loaded_pct'), 2)}% |"
        )

    L += ["", "## Cost (estimated)", "",
          "Not measured: no GPU benchmark was run. Architecture facts come from `modules/engines/*`; parameter counts "
          "and relative cost are approximate.", "",
          "| Model | Runtime | Architecture | Params | Input | Shared backbone | Relative cost | Observed median s (n) |",
          "|---|---|---|---|---|---|---|---|"]
    obs = costs.get("observed", {}).get("models", {})
    for c in costs["table"]:
        o = obs.get(c["model"])
        seen = f"{o['median_s']:.3f} ({o['n']})" if o else "—"
        L.append(f"| {c['model']} | {c['runtime']} | {c['architecture']} | {c['params_approx']} | {c['input']} | "
                 f"{c['shared_backbone']} | {c['relative_cost']} | {seen} |")
    if not costs.get("observed", {}).get("available"):
        L += ["", f"Observed timings: {costs.get('observed', {}).get('note', 'none found')}."]

    ref = [k for k in report["dimensions"] if report["roles"][k] not in ("candidate", "culling_candidate")]
    L += ["", "## Reference-only dimensions (no verdict)", "",
          "Composites are built from the candidates; `koniq` / `paq2piq` are deprecated and cover part of the library; "
          "`refcull_*` is a derived research family (`refcull_composite` is built from the others). Pairwise statistics "
          "involving them use only images scored by both sides.", ""]
    for k in ref:
        L.append(f"- `{k}` — {report['roles'][k]}, coverage {report['coverage_pct'][k]:.2f}%")

    th = report["thresholds"]
    L += [
        "", "## Rules (fixed before running)", "",
        f"- **Composite omittable:** Spearman ≥ {th['omit_min_spearman']} with the full composite, star ratings changed "
        f"< {th['omit_max_rating_change']:.0%} and colour labels changed < {th['omit_max_label_change']:.0%}.",
        f"- **Composite keep:** dropping changes ≥ {th['keep_min_output_change']:.0%} of the composite's output "
        "(ratings for `general`, labels for `technical` / `aesthetic`), or the model loads "
        f"≥ {th['keep_min_pca_loading']} on a component beyond PC1 with ≥ {th['keep_min_pca_explained']:.0%} of variance.",
        f"- **Culling keep:** within-stack variance share and consensus τ-b at or above the candidate median and tie rate "
        f"< {th['cull_keep_max_tie_rate']:.0%}; a keep with within-stack ρ ≥ {th['cull_omit_min_within_rho']} to a "
        "better-agreeing keep is demoted to omittable.",
        f"- **Culling omittable:** tie rate ≥ {th['cull_omit_min_tie_rate']:.0%}, or within-stack ρ ≥ "
        f"{th['cull_omit_min_within_rho']} with a kept model.",
        "- Everything else is **optional**.",
    ]
    if charts:
        L += ["", "## Charts", "", *[f"- [{Path(c).stem}]({c})" for c in charts]]
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------


def write_report(report: dict[str, Any], man: dict[str, Any], costs: dict[str, Any], m: data.ScoreMatrix,
                 out: Path, formats: set[str], charts: bool) -> list[str]:
    w = Writer(out, formats)
    w.json("manifest.json", man)
    w.json("report.json", {"manifest": man, "costs": costs, **report})
    verdict_rows = [{"scenario": sc, **{k: v for k, v in r.items() if k != "reasons"}, "reasons": "; ".join(r["reasons"])}
                    for sc, rows in report["verdicts"].items() for r in rows]
    w.csv("verdicts.csv", verdict_rows, list(dict.fromkeys(k for r in verdict_rows for k in r)))
    w.csv("ablation.csv", [{**r, "affects": ";".join(r["affects"])} for r in report["ablation"]])
    by_dim = {x["dimension"]: x for x in report["stacks"]["models"]}
    w.csv("stack_signals.csv", [
        {**by_dim.get(k, {"dimension": k}), "role": report["roles"][k],
         **{f"consensus_{f}": (report["consensus"]["models"].get(k) or {}).get(f)
            for f in ("kendall_tau_b", "kendall_tau_b_ci", "top1_agreement", "top_tied_rate", "stacks_defined")}}
        for k in report["dimensions"]
    ])
    fields = ["n", "missing_pct", "mean", "median", "std", "iqr", "skewness", "unique", "tie_fraction", "floor_pct",
              "ceiling_pct", "two_decimal_grid_pct", "entropy_norm", "bimodal_hint"]
    w.csv("profiles.csv", [{"dimension": k, "role": report["roles"][k], **{f: report["profiles"][k].get(f) for f in fields}}
                           for k in report["dimensions"]], ["dimension", "role", *fields])
    keys = report["correlation"]["keys"]
    for name in ("pooled_spearman", "within_spearman", "pooled_kendall_tau_b", "partial_pearson"):
        w.matrix_csv(f"correlation/{name}.csv", keys, report["correlation"][name]["r"])
    w.json("forward_selection.json", report["forward"])
    w.json("redundancy.json", report["redundancy"])
    w.csv("cost_estimates.csv", costs["table"])
    files = list(w.files)
    chart_files = write_charts(report, m, out) if charts else []
    (out / "REPORT.md").write_text(to_markdown(report, man, costs, chart_files), encoding="utf-8")
    return sorted(set(files)) + chart_files + ["REPORT.md"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, help="Output directory (default reports/model_selection/<UTC stamp>)")
    ap.add_argument("--keyword", help="Restrict to images tagged with this keyword")
    ap.add_argument("--min-size", type=int, default=2, help="Minimum images per stack")
    ap.add_argument("--bootstrap", type=int, default=200, help="Stack-bootstrap resamples for CIs")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timing-sample", type=int, default=5000, help="Recent scores_json rows scanned for timings")
    ap.add_argument("--no-charts", action="store_true", help="Skip SVG charts")
    ap.add_argument("--formats", default="csv,json")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    out = args.out or Path(project_root) / "reports" / "model_selection" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    full = data.load_matrix()
    m = data.scope_matrix(full, data.normalize_keyword(args.keyword))
    weights = sn.get_composite_weights()
    opts = {"min_size": args.min_size, "bootstrap": args.bootstrap, "seed": args.seed, "keyword": args.keyword,
            "weights": weights, "anchors": sn.get_percentile_anchors(), "rating_thresholds": sn.get_rating_thresholds(),
            "label_thresholds": sn.get_label_thresholds(), "thresholds": ms.THRESHOLDS}
    try:
        dictionary = labels.load_data_dictionary()
    except Exception as exc:
        logger.warning("data dictionary unavailable: %s", exc)
        dictionary = []
    logger.info("building report: %d images × %d dimensions", m.image_count, len(m.keys))
    report = ms.build_report(
        m, weights=weights, anchors=opts["anchors"], rating_thresholds=opts["rating_thresholds"],
        label_thresholds=opts["label_thresholds"], min_size=args.min_size, bootstrap=args.bootstrap, seed=args.seed,
        data_dictionary=dictionary,
    )
    try:
        observed = observed_timings(args.timing_sample)
    except Exception as exc:
        observed = {"available": False, "note": f"timing lookup failed: {exc}"}
    costs = {"table": COST_TABLE, "observed": observed, "estimated": True}
    files = write_report(report, manifest(m, opts), costs, m, out, formats, charts=not args.no_charts)
    logger.info("wrote %d files to %s", len(files), out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
