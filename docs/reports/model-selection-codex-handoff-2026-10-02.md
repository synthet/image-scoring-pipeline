---
type: Report
title: Model selection study — Codex handoff (2026-10-02)
description: Handoff from Codex session export codex-session-01a0f9fc-13f8-7da1-938a-6c19ddbe5f60_2.md — frozen snapshot, blind review sample, exploratory REPORT, and how it relates to the label-free model_selection_report bundle.
resource: reports/model-selection-codex-handoff-2026-10-02.md
tags: [report, scoring, culling, analytics, model-selection, codex]
timestamp: 2026-10-02T00:00:00Z
okf_version: 0.1
status: active
---

# Model selection study — Codex handoff (2026-10-02)

**Transcript archive:** [`codex-session-01a0f9fc-13f8-7da1-938a-6c19ddbe5f60_2.md`](../../codex-session-01a0f9fc-13f8-7da1-938a-6c19ddbe5f60_2.md) (repo root; not indexed in wiki body).

**Purpose:** freeze the production corpus, define a **blind human review** sample, and emit **exploratory** library statistics before any labels exist. This path does **not** change fusion weights or culling code.

## Frozen study bundle

| File | Role |
|------|------|
| [`reports/model-selection-2026-10-01/snapshot.json.gz`](../../reports/model-selection-2026-10-01/snapshot.json.gz) | 77,331 images; repeatable-read PostgreSQL export |
| [`reports/model-selection-2026-10-01/sample.json`](../../reports/model-selection-2026-10-01/sample.json) | Stratified review units + splits |
| [`reports/model-selection-2026-10-01/manifest.json`](../../reports/model-selection-2026-10-01/manifest.json) | Content hashes |
| [`reports/model-selection-2026-10-01/reviews.jsonl`](../../reports/model-selection-2026-10-01/reviews.jsonl) | Append-only labels (**empty** at handoff) |
| [`reports/model-selection-2026-10-01/REPORT.md`](../../reports/model-selection-2026-10-01/REPORT.md) | Exploratory evidence markdown |
| [`reports/model-selection-2026-10-01/correlations.csv`](../../reports/model-selection-2026-10-01/correlations.csv) | Pairwise ρ tables |
| [`reports/model-selection-2026-10-01/profiles.csv`](../../reports/model-selection-2026-10-01/profiles.csv) | Coverage / tie profiles |

### Fingerprints (`manifest.json`)

| Field | SHA-256 (prefix) |
|-------|------------------|
| `snapshot_sha256` | `fe26c0e7710362424e123fc42f75ad911c2b41bd468c66896e31467d4c9fe7fa` |
| `sample_sha256` | `345946813ec5e84100f41937a2bc9cc9727ae27134ae65083d0ef449b109b660` |
| `created_at` | `2026-10-02T00:52:09.639766+00:00` |
| `git_sha` | `unavailable-in-container` when `create` ran inside gpu-shell without `git` |

## Review design (900 units)

| Kind | Count | Notes |
|------|------:|-------|
| Single (Track A) | 600 | Subject × quality quartile × camera strata |
| Stack groups | 174 | Multi-image stacks |
| Burst groups | 126 | Burst sources |
| Hidden consistency repeats | 90 | Not counted in progress totals separately |
| **Progress total** | **900** | `progress` reports 600 singles + 300 stack/burst groups |

Splits (hash-based, session blocks preserved): train / validation / test. **Labels start empty**; automatic ratings and picks are excluded from the review UI.

## Code and verification

| Component | Path |
|-----------|------|
| Study logic | `modules/score_analytics/study.py`, `study_data.py`, `study_report.py`, `study_review.py` |
| CLI | [`scripts/analysis/model_selection_study.py`](../../scripts/analysis/model_selection_study.py) — `create`, `serve`, `explore`, `progress`, `benchmark` |
| Tests | `tests/test_model_selection_study.py` — **8/8 passed** in gpu-shell (`--noconftest`) at handoff |

### Implementation notes from Codex

- Postgres pool: `rollback()` before `REPEATABLE READ` readonly snapshot (fixes pooled-connection state).
- `create`: tolerate missing `git` in container (`shutil.which`).
- `explore`: within-stack pairwise audit uses the **first 300 stacks** (of 11,174) so export finishes in bounded time; full-library pooled ρ still uses all images.

## Exploratory findings (not omission decisions)

From [`reports/model-selection-2026-10-01/REPORT.md`](../../reports/model-selection-2026-10-01/REPORT.md):

- Strongest library pairs: `liqe`/`topiq` ρ≈0.662; `koniq`/`paq2piq` ρ≈0.589 (legacy, 49% coverage).
- Within-stack audit (300 stacks): `liqe`/`topiq` ρ≈0.266; `arniqa`/`liqe` ρ≈0.105 — global redundancy does not imply burst redundancy.
- `refcull_*`: very high tie rates in stacks (e.g. focus/noise 46–51%); treat as one research family, not independent models.
- Runtime: normalized score table has **no timing column** — use `benchmark`, not zero-filled costs.
- `study.omission_decision()` returns **`needs human labels`** until independent test blocks and review coverage support non-inferiority.

## Commands

```powershell
# Blind review (port 7862 avoids WebUI 7860)
docker exec image-scoring-gpu-shell python scripts/analysis/model_selection_study.py serve --study reports/model-selection-2026-10-01 --port 7862

docker exec image-scoring-gpu-shell python scripts/analysis/model_selection_study.py progress --study reports/model-selection-2026-10-01
docker exec image-scoring-gpu-shell python scripts/analysis/model_selection_study.py explore --study reports/model-selection-2026-10-01
docker exec image-scoring-gpu-shell python scripts/analysis/model_selection_study.py benchmark --study reports/model-selection-2026-10-01
```

## How this relates to other artifacts

| Question | Use |
|----------|-----|
| Keep/omit composites & full-stack culling stats (label-free rules) | [`reports/model_selection/latest/REPORT.md`](../../reports/model_selection/latest/REPORT.md) via [`scripts/analysis/model_selection_report.py`](../../scripts/analysis/model_selection_report.py) |
| Production change roadmap (Phase 1–3) | [model_evaluation_and_curation_plan.md](model_evaluation_and_curation_plan.md) |
| Cursor session (label-free implementation) | [model-selection-session-2026-10-01.md](model-selection-session-2026-10-01.md) |
| Executive findings snapshot | [model-selection-findings-2026-10-02.md](model-selection-findings-2026-10-02.md) |

**Promotion gate (human labels):** minimum **150** completed stack/burst groups and **300** completed singles before fitting weights or changing production thresholds (see curation plan).
