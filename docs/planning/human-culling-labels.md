---
type: Plan
title: Human culling label set — sampling design, label semantics, storage and evaluation
description: Protocol for the ~300-group human culling label set (#415): stratified, weighted sample of backend stacks and 0.5 s bursts; blind per-frame pick/keep/reject plus one best frame; stored in a dedicated human_labels schema; evaluation metrics and gates. 302 groups sampled, 20 labelled as of 2026-09-25.
resource: docs/planning/human-culling-labels.md
tags: [planning, culling, labels, evaluation, bursts, stacks, clean-room]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
status: in-progress
---

# Human culling label set (#415)

> **Provenance:** derived from competitive analysis of a commercial application's observable behaviour
> and documentation; contains no code, identifiers, fitted constants or model artefacts from it. The
> **labels are the owner's own judgements** and are usable anywhere. Only the *choice of groups* used
> signals from a local research instrument (a behavioural reimplementation of a reference
> wildlife-culling design). All counts and thresholds below are **starting points to re-fit**.

Related: roadmap item 0 of [subject-aware culling evidence](subject-aware-culling-evidence.md) ·
[within-burst evidence plan](within-burst-evidence-plan.md) ·
[reference culling shadow scores](../reports/reference-culling-shadow-scores-2026-09-25.md) ·
[model suitability labels](../features/implemented/11-score-analytics-and-model-suitability.md)

## Why

No independent culling labels exist. `images.pick_status` mirrors `cull_decision`, derived from
`score_general`; `stacks.best_image_id` comes from the same score; the non-auto `culling_picks` rows carry
no decision; the 236-frame bird-crop set is agent-labelled. Every culling comparison so far (Arm A vs B,
reference scores vs production) therefore measures agreement, not accuracy.

## Unit of labelling

A **group** is a set of 2–12 frames of one moment, drawn from two sources so that both groupings can be
evaluated:

| Source | Definition |
|---|---|
| `stack` | A backend stack (`images.stack_id`) |
| `burst` | A time-gap burst (0.5 s split) that is not identical to a stack |

Groups larger than 12 are excluded: a person cannot compare more frames reliably, and they are rare.

## Sampling design (v1)

- **Candidates:** 16,341 groups.
- **Strata (36 cells):** source × dominant subject (bird / other / none, by majority of frames) × size
  (2 / 3–5 / 6–12) × whether the reference composite and `score_general` pick the same best frame.
- **Allocation:** proportional to √(cell population), with a floor of 3 per non-empty cell, so rare cells
  (no-subject bursts of 6–12, for example) are still represented.
- **Spread:** at most 2 groups per folder and source, which spreads dates, cameras and lenses.
- **Weights:** each group stores `weight = cell population / sampled in cell`. Library-level estimates must
  use these weights; unweighted numbers describe the sample only.
- **Order:** shuffled across strata, so a partially labelled set is still roughly balanced.
- **Result:** 302 groups, 1,238 frames.

**Deviation from #415:** the issue asks for subject-size terciles. The v1 strata use subject type instead;
subject size is recorded per frame (box area, fill fraction) and can be used for post-stratification. If
the size terciles turn out to be under-covered, draw a v2 top-up sample for the thin cells rather than
re-sampling.

## Label semantics

For each group, the labeller:

1. grades **every frame**: `2 = pick` (would keep and use), `1 = keep` (acceptable, not first choice),
   `0 = reject` (would delete);
2. marks **one best frame**: "if you could keep only one". It must be a pick. Only an all-reject group may
   have no best frame;
3. may **skip** a group (for example a wrong grouping or identical frames) and leave a note.

These map onto the grading already used by the suitability toolkit (pick = 2 > keep = 1 > reject = 0),
so pairwise accuracy, top-1 and NDCG can be computed without translation.

## Labelling tool — required behaviour

The first tool is a local web page run from the research workspace. Any in-app version (see the gallery's
planned labelling mode) must keep these properties:

- **Blind:** no model scores, ranks, filenames or strata are visible. Frames appear in capture order.
- **Per-frame grading and one best frame**, with keyboard shortcuts, and bulk grading of the remaining
  ungraded frames.
- **Full-resolution loupe** with click-to-100 % and **flip compare**: moving to the next frame keeps the
  same zoom and position, so eye sharpness can be compared directly.
- **Validation on save:** every frame graded, at most one best, best is a pick, a best frame unless all
  are rejected.
- **Resumable, multi-labeller:** labels are keyed by labeller name; time spent per group is recorded.
- **Saved on every submit** to the database and to an append-only JSONL log.

## Storage

A dedicated schema, `human_labels`, separate from any research schema, so dropping research data can never
delete labels:

| Table | Columns |
|---|---|
| `human_labels.units` | `unit_id`, `unit_key` (`stack:<id>` or `burst:<id>`), `source`, `image_ids int[]`, `strata jsonb`, `weight`, `sample_order`, `sample_version` |
| `human_labels.labels` | `unit_id`, `image_id`, `labeler`, `grade` (0–2), `is_best`, `updated_at` |
| `human_labels.unit_status` | `unit_id`, `labeler`, `status` (`done` / `skipped`), `note`, `seconds`, `updated_at` |

Snapshots: `pg_dump -n human_labels` plus a flat CSV export after each labelling session.

**Integration (proposed):** the suitability toolkit's label audit (`labels.py`) treats non-auto
`culling_picks` as the only independent labels. Either teach it to read `human_labels` directly (preferred:
keeps groups and weights), or export done groups into `culling_picks` with a dedicated session. Decide
before the first evaluation run.

## Evaluation plan

Per model and per score dimension, on done groups, weighted by `weight`, with group-bootstrap CIs:

- **pairwise accuracy** over within-group pairs with different grades (each group weighted equally
  inside its stratum);
- **top-1:** the model's top frame is the human best frame; also "top frame is a pick";
- **pick-vs-reject AUC** within groups;
- **by stratum:** subject type, size bucket, source, and the agree / disagree cells, which directly test
  whether the reference composite or `score_general` is right when they disagree.

**Gate (starting point):** do not change production culling on fewer than ~150 done groups or when the CI
of the difference between two candidates spans zero.

## Status (2026-09-25)

- 302 groups sampled (sample v1).
- **20 groups done** by one labeller: 60 frames, 20 picks, 16 keeps, 24 rejects, 17 best frames; about
  23 s per group, so the full set is roughly 2 hours of labelling.
- Labels are snapshotted (schema dump + CSV). Too few for evaluation yet.

## Next

1. Finish labelling (target ≥ 150 done groups before the first evaluation).
2. A second labeller on a 30-group overlap to measure inter-rater agreement (Cohen's κ on grades,
   best-frame agreement); the model ceiling is the human agreement.
3. Run the evaluation above; publish as a report and update the Stage 6 gates in
   [subject-aware culling evidence](subject-aware-culling-evidence.md).
