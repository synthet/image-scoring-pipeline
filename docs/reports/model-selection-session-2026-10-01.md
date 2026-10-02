---
type: Report
title: Label-free model selection report — session summary
description: Session record for label-free model selection (2026-10-01). Implementation notes, links to reports/model_selection/latest, Codex study handoff, next commands, and draft backlog issue.
resource: reports/model-selection-session-2026-10-01.md
tags: [report, session, scoring, culling, analytics, model-selection]
timestamp: 2026-10-01T00:00:00Z
okf_version: 0.1
status: active
---

# Label-free model selection report — session summary (2026-10-01)

**Goal:** rate each scoring model on several statistical criteria, then decide which models can be left out of the `general`, `technical` and `aesthetic` composites and of stack/burst culling. The output is the smallest reliable model set for each scenario.

**Status (updated 2026-10-02):** label-free code and tests are in repo. The **live report has been generated** at [`reports/model_selection/latest/REPORT.md`](../../reports/model_selection/latest/REPORT.md) (also summarized in [findings snapshot](model-selection-findings-2026-10-02.md)). In parallel, Codex froze the **human study** bundle under `reports/model-selection-2026-10-01/` — see [Codex handoff](model-selection-codex-handoff-2026-10-02.md) and transcript [`codex-session-01a0f9fc-13f8-7da1-938a-6c19ddbe5f60_2.md`](../../codex-session-01a0f9fc-13f8-7da1-938a-6c19ddbe5f60_2.md). **Reviews: 0 / 900** units labeled. Phase 1 production changes remain in [curation plan](model_evaluation_and_curation_plan.md) pending owner decisions. The Cursor shell-hook blocker may still affect local runs; use gpu-shell/docker exec as in the handoff doc.

**Decisions made with the owner:**
- **No human labels:** only score statistics, distributions and charts are used.
- **Offline report only:** no API, `/ui/scores` tab or OpenAPI change.
- **No GPU benchmark:** cost is estimated, not measured.
- **Read-only:** weight changes in `scoring.fusion` are a separate follow-up.

## Live-data facts (from the parallel Codex session, `/api/analytics/scores/*`)

| Fact | Value |
|---|---|
| Images | 77,331 |
| Stacks (≥ 2 images) | 11,174 stacks, 66,308 images, 9,575 with picks |
| Full-coverage production models | `liqe`, `spaq`, `topiq`, `arniqa`, `ava` (100%); `clip_quality_v0` 99.95% |
| Legacy, partial coverage | `koniq`, `paq2piq` — 49.18% |
| Derived research family | seven `refcull_*` dimensions, 99.31% (`refcull_composite` is built from the others) |

Models agree much less inside a stack than across the library:

| Pair | Library Spearman | Within-stack Spearman |
|---|---|---|
| liqe / topiq | 0.66 | ≈ 0.29 |
| arniqa / liqe | 0.59 | ≈ 0.14 |
| koniq / spaq | 0.56 | ≈ 0.22 |

So a model that looks redundant library-wide can still matter for culling. Global and culling verdicts are therefore separate. `images.pick_status`, `cull_decision` and `stacks.best_image_id` all come from `score_general` ([human culling labels](../planning/human-culling-labels.md)), so agreement with them is agreement with production, not accuracy.

## What was built

| File | Role |
|---|---|
| [`modules/score_analytics/model_selection.py`](../../modules/score_analytics/model_selection.py) | Pure numpy. Vectorized composite, rating and label mirror of `score_normalization`. Drop-one composite ablation, leave-one-out within-stack consensus (Kendall τ-b, top-1, stack-bootstrap CIs), redundancy groups, greedy forward selection, keep / optional / omittable rules (`THRESHOLDS`), `build_report` |
| [`scripts/analysis/model_selection_report.py`](../../scripts/analysis/model_selection_report.py) | Loads the score matrix and writes `REPORT.md`, CSV/JSON and SVG charts to `reports/model_selection/<UTC stamp>/`. Static estimated cost table. Never writes to the database |
| [`tests/test_model_selection.py`](../../tests/test_model_selection.py) | 8 planned synthetic tests plus a database-free smoke test of the report writer |
| [Feature doc 11](../features/implemented/11-score-analytics-and-model-suitability.md#model-selection-report-label-free), [`log.md`](../log.md) | Documentation |

**Verdict roles:**
- Only `liqe`, `spaq`, `topiq`, `arniqa` and `ava` get verdicts; `clip_quality_v0` gets one for culling only.
- Reference only: `koniq`, `paq2piq`, the `refcull_*` family and the composites.
- Every verdict carries "Statistical only; not validated against human judgments".

**Decision rules (fixed before running):**
- **Composite omittable:** without the model, the composite keeps Spearman ≥ 0.98 with the full one, and fewer than 2% of star ratings and fewer than 2% of colour labels change.
- **Composite keep:** dropping the model changes ≥ 5% of the composite's output, or the model loads ≥ 0.4 on a component beyond PC1 that explains ≥ 10% of variance.
- **Culling keep:** within-stack variance share and consensus τ-b both at or above the candidate median, and a tie rate under 20%. A kept model correlating ρ ≥ 0.8 within stacks with a better kept model is demoted.
- **Culling omittable:** tie rate ≥ 50%, or within-stack ρ ≥ 0.8 with a kept model.
- **Forward selection:** adds models until the next one improves the target by less than 0.01, with a maximum of 3.

## Deviations from the plan

- **Charts are standalone SVG, not matplotlib PNG.** Nothing in the repo uses or lists matplotlib, so its availability in gpu-shell was unconfirmed.
- **Agreement with the production best frame** reuses the existing `best_match_rate` from `stacks.analyze_stacks`; no new function.
- **Tie rate counts identical stored values** (`EXACT_TIE_EPS = 1e-6`). The default 0.01 tolerance would penalise narrow-range models such as AVA.
- **Observed timings are read only if `images.scores_json` exists.** The column is absent from the PostgreSQL DDL, so the cost table is likely estimates only.

## Blocker: shell hook

Cursor imports the Claude Code hooks in [`.claude/settings.json`](../../.claude/settings.json). Their commands used `"$CLAUDE_PROJECT_DIR/scripts/agent_harness/hook.py"`. In the shell Cursor uses for hooks (apparently PowerShell), `$CLAUDE_PROJECT_DIR` is an undefined shell variable, so the path collapsed to `D:\scripts\agent_harness\hook.py` and every command was rejected.

With owner approval, the four hook commands now use the relative path `python scripts/agent_harness/hook.py …`, which works in both bash and PowerShell. The error was unchanged afterwards. Either Cursor had not reloaded the file, or it runs these hooks from `D:\`, which would need an absolute path. **Next step:** reload Cursor and check the Hooks output channel.

## Next steps

```powershell
ruff check modules/score_analytics/model_selection.py scripts/analysis/model_selection_report.py tests/test_model_selection.py
.\scripts\powershell\Invoke-GpuShell.ps1 python -m pytest tests/test_model_selection.py -q --tb=short
.\scripts\powershell\Invoke-GpuShell.ps1 python scripts/analysis/model_selection_report.py --out reports/model_selection/latest
docker exec image-scoring-gpu-shell python scripts/analysis/model_selection_study.py serve --study reports/model-selection-2026-10-01 --port 7862
```

File the draft backlog issue below when ready. Regenerate the label-free bundle after any `scoring.fusion` change.

## Related work

The Codex session also added a frozen, human-labelled study: [`scripts/analysis/model_selection_study.py`](../../scripts/analysis/model_selection_study.py) and `modules/score_analytics/study*.py`. It has `create`, `serve`, `select`, `test` and `benchmark` commands. That study, together with the human culling label set (#415), is the path to accuracy claims. This label-free report does not replace it.

## Draft backlog issue

**Title:** `feat(analytics): label-free model selection report (keep/omit per scenario)`

**Labels:** `enhancement`, `analytics`, `scoring`, `priority:p2` · **Board:** Stage = Ready → Claimed

```markdown
## Goal
Rate each scoring model on statistical criteria and decide which models can be omitted from the
`general` / `technical` / `aesthetic` composites and from stack/burst culling, without human labels.
Follow-up to #393 (score analytics). Complements the human-labelled study (#415).

## Scope
- `modules/score_analytics/model_selection.py`: composite drop-one ablation (Spearman, star-rating /
  colour-label change, top-10% overlap, stack best-frame change), within-stack consensus τ-b / top-1
  with stack-bootstrap CIs, redundancy groups (library vs within-stack), forward selection,
  prespecified keep / optional / omittable rules.
- `scripts/analysis/model_selection_report.py`: REPORT.md + CSV/JSON + SVG charts under
  `reports/model_selection/<stamp>/`; static estimated cost table. Read-only.
- `tests/test_model_selection.py` (fast subset, synthetic data).
- Docs: feature doc 11 section, `docs/log.md`, findings report under `docs/reports/`.

## Out of scope
- Changing `scoring.fusion` weights (separate issue; needs `recalc_composite_scores.py` + gallery check).
- `/ui/scores` tab or new API endpoint.
- GPU latency benchmark.

## Acceptance criteria
- AC-1: `pytest tests/test_model_selection.py` passes in gpu-shell; ruff clean on new files.
- AC-2: Report runs against the live DB without writes and lists a verdict for every production model in
  every scenario, plus 1/2/3-model recommended sets.
- AC-3: Every verdict carries the "statistical only" caveat; koniq/paq2piq, refcull_* and composites get no verdict.
- AC-4: Findings written to `docs/reports/model-selection-<date>.md` and indexed.
```
