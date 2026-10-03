---
type: Report
title: Model selection — findings snapshot (2026-10-02)
description: Short wiki snapshot of label-free verdicts and exploratory study stats. Statistical only; not validated against human judgments. Links to machine-readable REPORT bundles.
resource: reports/model-selection-findings-2026-10-02.md
tags: [report, scoring, culling, analytics, model-selection]
timestamp: 2026-10-02T00:00:00Z
okf_version: 0.2
status: active
---

# Model selection — findings snapshot (2026-10-02)

> **Statistical only; not validated against human judgments.** Production pick/best-frame fields agree with current `score_general`, not ground truth. See [Codex handoff](model-selection-codex-handoff-2026-10-02.md) for the blind review path.

**Corpus:** 77,331 images · 11,174 stacks (66,308 images).

## Authoritative outputs

| Bundle | When to cite |
|--------|----------------|
| [`reports/model_selection/latest/REPORT.md`](../../reports/model_selection/latest/REPORT.md) | Composite ablation, forward selection, verdicts, **all 11,174 stacks** |
| [`reports/model-selection-2026-10-01/REPORT.md`](../../reports/model-selection-2026-10-01/REPORT.md) | Pre-label exploratory stats; within-stack ρ on **300-stack audit** |
| [model_evaluation_and_curation_plan.md](model_evaluation_and_curation_plan.md) | Proposed Phase 1–3 config/culling changes (needs owner approval) |

## Minimal model sets (label-free forward select)

| Scenario | 1 model | 2 models | 3 models |
|----------|---------|----------|----------|
| General | liqe (0.836) | liqe + spaq (0.978) | — (stop: +ava &lt; 0.01) |
| Technical | topiq (0.843) | topiq + arniqa (0.909) | + spaq (0.970) |
| Aesthetic | spaq (0.872) | spaq + ava (0.992) | — (stop: +liqe &lt; 0.01) |
| Culling consensus τ-b | topiq (0.524) | topiq + liqe (0.677) | + ava (0.714) |

## Verdict highlights (`model_selection_report`)

| Area | Keep / core | Optional / omit candidate |
|------|-------------|---------------------------|
| **General** | liqe, spaq, ava, topiq | arniqa (ρ 0.9958 without it; 6.8% stars change) |
| **Technical** | all four active models | — |
| **Aesthetic** | spaq, ava | liqe (**optional**) |
| **Culling (rules)** | topiq | liqe, spaq, arniqa, ava, clip — optional by threshold; differs from pick-AUC narrative |

## Deprecation hypotheses (not promoted without labels)

- **koniq / paq2piq:** ~49% coverage; high library collinearity; weak burst signal in suitability/exploratory tables.
- **refcull_* (7):** shadow research family; high stack ties; do not treat as independent fusion inputs.
- **arniqa:** smallest general composite ablation delta. The static table put it slowest (~115 ms), but measured 2026-10-02 on an RTX 4060 Laptop GPU: per-model `predict()` mean spaq 42.6 / ava 37.8 / topiq 37.4 / liqe 33.1 / **arniqa 28.6 ms**; ensemble 179.5 → 150.9 ms without `arniqa`, i.e. **~16% of model time** (less end to end, since RAW decode and IO are unchanged) — #494; candidate for `high_throughput` profile only after config issue.

## Correlation theme

Library Spearman **overstates** agreement inside bursts (e.g. liqe×topiq ~0.66 library vs ~0.27–0.31 within-stack depending on audit size). Separate **composite** verdicts from **culling** verdicts.

## Next steps

1. Run blind review: `model_selection_study.py serve` (see handoff doc).
2. Owner decisions on Phase 1 in curation plan (refcull compute, culling rank formula, arniqa profile).
3. Regenerate label-free bundle after fusion changes: `python scripts/analysis/model_selection_report.py`.
