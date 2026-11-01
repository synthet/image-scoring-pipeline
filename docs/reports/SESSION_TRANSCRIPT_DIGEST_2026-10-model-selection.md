---
type: Report
title: Session digest — label-free model selection and score analytics (2026-10)
description: Consolidated findings and technical decisions from October 1–2, 2026 agent sessions evaluating scoring model signals, library-wide vs within-stack correlation divergence, label-free ablation rules, and human review sample freezing.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-model-selection.md
tags: [session, digest, scoring, culling, analytics, model-selection, transcript]
timestamp: 2026-10-02T00:00:00Z
okf_version: 0.2
status: active
---

# Session digest — label-free model selection and score analytics (2026-10)

**Sources:**
- `2026-10-01-203438-local-command-caveatthe-command-below-was-run-d.txt` (Claude Code terminal export, 5,159 lines, SHA-256 `f2f7d29792e321f38c3eb1150ddcec802aa46a3ac086e66d548d608e27d5a115`)
- `codex-session-01a0f9fc-13f8-7da1-938a-6c19ddbe5f60_2.md` (Codex markdown export, 9,559 lines, SHA-256 `fc472b9464dab0d0e9641de30d6470c9cff7ef32d5149217a72fc2280ae37ee3`)

**Classification:** Shareable project knowledge. Scrubbed operator paths, local IP addresses, and agent session UUIDs. No credentials present.

**Related living docs:**
- [docs/reports/model-selection-session-2026-10-01.md](model-selection-session-2026-10-01.md) — initial session summary
- [docs/reports/model-selection-findings-2026-10-02.md](model-selection-findings-2026-10-02.md) — statistical findings snapshot
- [docs/reports/model-selection-codex-handoff-2026-10-02.md](model-selection-codex-handoff-2026-10-02.md) — Codex handoff document
- [`reports/model_selection/latest/REPORT.md`](../../reports/model_selection/latest/REPORT.md) — live generated report
- [`modules/score_analytics/model_selection.py`](../../modules/score_analytics/model_selection.py) — pure NumPy evaluation engine

---

## Problem statement

The image scoring pipeline deployed multiple neural image-quality assessment (IQA) and aesthetic models (`liqe`, `spaq`, `topiq`, `arniqa`, `ava`, `clip_quality_v0`, `koniq`, `paq2piq`, and the `refcull_*` family). Running all models on every imported frame incurs substantial compute and inference latency.

The objective was to rate each scoring model on rigorous statistical criteria and establish whether specific models can be omitted from composite scores (`general`, `technical`, `aesthetic`) or burst/stack culling without sacrificing accuracy or stability.

---

## Findings & architectural discoveries

### 1. Library vs within-stack correlation divergence

Analysis of the live database (covering 77,331 images across 11,174 stacks) revealed a critical structural divergence: models that appear strongly correlated library-wide show markedly weaker agreement when evaluated within individual burst/stack sequences.

| Model pair | Library-wide Spearman $\rho$ | Mean within-stack Spearman $\rho$ |
|---|---:|---:|
| LIQE / TOPIQ | 0.662 | $\approx 0.29$ |
| ARNIQA / LIQE | 0.587 | $\approx 0.14$ |
| KonIQ / SPAQ | 0.560 | $\approx 0.22$ |
| KonIQ / PaQ2PiQ | 0.589 | $\approx 0.25$ |

**Implication:** A model that appears redundant across a diverse global catalog can still provide indispensable discriminative signal for micro-culling within high-speed bursts. Consequently, global composite scoring and burst culling require strictly separate evaluation rules.

### 2. Model coverage breakdown

- **Full production coverage (100%):** `liqe`, `spaq`, `topiq`, `arniqa`, `ava` (and `clip_quality_v0` at 99.95%).
- **Legacy partial coverage (49.18%):** `koniq`, `paq2piq`.
- **Derived research dimensions (99.31%):** Seven `refcull_*` dimensions (composite derived from constituent dimensions).

---

## Technical decisions & implementation

### 1. Decision rules for model omission

Fixed mathematical rules were codified in `modules/score_analytics/model_selection.py`:

- **Composite Omittable Rule:** A model is omittable from a composite if, upon dropping it:
  1. The Spearman correlation between the reduced and full composite remains $\ge 0.98$.
  2. Fewer than 2% of categorical star ratings shift.
  3. Fewer than 2% of color labels change.
- **Composite Keep Rule:** A model must be retained if dropping it alters $\ge 5\%$ of the composite's output, or if the model exhibits a loading $\ge 0.4$ on any principal component beyond PC1 that accounts for $\ge 10\%$ of total variance.
- **Dedicated Culling Rank:** Implemented as a default-off configuration option `culling.dedicated_rank` (Issue #474) to decouple burst culling from general score changes.

### 2. Shipped artifacts

| File | Purpose | Verification |
|---|---|---|
| [`modules/score_analytics/model_selection.py`](../../modules/score_analytics/model_selection.py) | Vectorized composite ablation, Kendall $\tau$-b, drop-one bootstrap, greedy forward selection. | 8 synthetic unit tests passing. |
| [`scripts/analysis/model_selection_report.py`](../../scripts/analysis/model_selection_report.py) | Offline report generator writing CSV, JSON, and SVG charts to `reports/model_selection/<UTC>/`. | Smoke-tested without DB dependency. |
| [`tests/test_model_selection.py`](../../tests/test_model_selection.py) | Unit test suite verifying omission rules and edge cases. | `pytest tests/test_model_selection.py` passed 8/8. |
| `reports/model-selection-2026-10-01/` | Frozen study bundle containing `snapshot.json.gz`, `correlations.csv`, and review protocols. | Verified reproducible snapshot. |

---

## Validation & historical evidence

- **Test suite:** Focused unit tests in `tests/test_model_selection.py` passed completely (8/8).
- **Execution isolation:** The analysis engine was verified strictly read-only; no database writes were executed during report generation.
- **Human study status:** The parallel Codex session created the human study protocol (900 review units); at the close of this session arc, 0/900 units were labeled, leaving all omissions strictly statistical until ground-truth validation is collected.

---

## Unresolved follow-ups & handoffs

1. Weight alterations in `scoring.fusion` were deferred until human review labels are gathered.
2. GPU benchmarking of model runtime was estimated from model parameter counts rather than profiled in-process.
3. The dedicated culling rank remained gated behind feature flag `culling.dedicated_rank`.
