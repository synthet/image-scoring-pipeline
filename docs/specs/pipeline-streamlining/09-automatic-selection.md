---
type: Feature Spec
title: "Spec 09: automatic selection for new bird runs"
description: A versioned standalone rule that turns each new detected v1 bird run into an active selection, or records why not, in every lane, so species reads one box path without a manual promotion step.
resource: docs/specs/pipeline-streamlining/09-automatic-selection.md
tags: [specs, localization, selection, species, automation]
timestamp: 2026-11-20T00:00:00Z
okf_version: 0.2
status: draft
---

# Spec 09: automatic selection for new bird runs

**Issue:** #867 · **Hub:** [INDEX.md](INDEX.md) · **Epic:** #345 · **Depends on:** #810 (v0 re-detection), #858, #869

**Status:** draft. D1, D2 and D4–D6 are decided (see [§ Decisions](#decisions)). D3, the confidence threshold, is still the owner's, and the rule isn't enabled until it is set.

## Summary

This is acceptance criterion AC5 of the [localization reassessment](../../planning/localization-reassessment-2026-11-12.md), which comes from requirement R6: new bird-tagged images get a selection with no manual tranche or manifest step.

Today a selection exists only where a one-off promotion wrote it (#472, #694, the v1 re-gate rules). New images get a current `bird` run but no selection, so species keeps using the embedded detector for them, and #638 can't retire it.

This spec adds one versioned standalone rule. It runs inside `write_run` (`modules/localization.py:417`), the one place every lane persists a run. For each new current v1 run, the rule either selects the rank-0 region through the existing `select_region` (`modules/localization_selection.py:109`) or records a reason code. No judge, Jev call or human label runs in production (R6).

## Consumer outcome and what stays blocked (#859)

- **Consumer:** species. It is the only live reader of selections (#857, D1). `read_bird_bbox` returns the active selection first, then the legacy payload, then the column.
- **Outcome protected:** the species stored outcome (top-1 label, or abstention). A framing or box-tightness standard is not the gate: no live reader is sensitive to it (#857, F2).
- **When the outcome changes:** while the embedded detector is on, it runs the same `bird_detect_v1` at 0.25 and takes the highest-confidence box. So a selected or declined v1 frame gives species the same box. Species also does not re-run when a selection appears: stored species changes only on an overwrite run, or for images not yet classified (`modules/phases_policy.py`). The rule starts to matter for species output when #638 retires the embedded detector, because frames without a selection then abstain with `no_bird_box` (#869).
- **If something goes wrong:** one command revokes every selection by its `selected_by` (AC-9). That restores the previous `bird_bbox`.
- **Iteration count:** species parity between a selection box and the embedded detector has already run seven times on this metric: the #858 pilot, then #810 batches 1–6. On 2026-11-15 the owner said parity is not the criterion. This spec adds no eighth round (D1).
- **Policy owner:** the owner delegated D1, D2 and D4–D6 to sub-agent research plus Jev on 2026-11-20 (receipt below). D3 stays the owner's.
- **Resolution:** the existing evidence is reported with its interval and its limit in [§ Evidence](#evidence).

## Current state (2026-11-20, local database)

| Bird-tagged images (keyword `bird`/`birds`) | Images | With an active selection |
|---|---:|---:|
| Current v1 run, `detected` | ~23,740 | 4,628 |
| Current v0 run, `detected` (#810 is re-detecting these) | ~10,100 | 0 |
| Current v1 run, `no_detection` | ~5,180 | 0 |
| Current v1 run, `disabled` (scene-route skip) | ~164 | 0 |

The counts move while #810 runs. Every bird-tagged image has a scene label (#809).

- **Existing selections:** they come from `v1_regate_rule/3` (4,375), `v1_regate_rule/4` (273) and `bbox_review_20261023/jev` (19).
- **They all point at non-current runs:** all 4,667 active selections point at runs that are no longer current. That's by design, because promotion wrote `publish=False` artifact runs.
- **One active selection per image:** a unique index enforces it (`ux_ils_active_image_detector (image_id, detector_key) WHERE revoked_at IS NULL`).

## Evidence

- **Species outcome on v1 runs:** in #810's per-batch parity, the new v1 run's box (`region:box`) against the embedded detector (`.agent/scratch/redetect-810/run_batches.sh`) gave **600/600** top-1 agreement over batches 1–6, with median box IoU 0.999. The #858 pilot's v1 subset gave 54/54. Both arms run the same detector, so this shows "no loss" (R3) but cannot separate outcome from bar.
- **Limit:** #810's samples are freshly re-detected frames. The older v1 runs, the pool D5 would backfill, are covered only by the 54 #858 pairs (Wilson lower bound 0.934).
- **v1 box correctness by rank-0 confidence:** from the #879 owner labels, raw counts. The bins were not preregistered.

| Confidence | Boxes not on a bird |
|---|---:|
| 0.25–0.4 | 3/6 |
| 0.4–0.6 | 6/11 |
| 0.6–0.8 | 3/17 |
| ≥ 0.8 | 4/92 |
| below 0.6, pooled | 9/17 (Wilson 0.31–0.74) |
| 0.6 and above, pooled | 7/109 (0.03–0.13) |

- **Size of the pool below a threshold:** of about 19,120 current v1 `detected` bird-tagged images without a selection, 2,117 have rank-0 confidence below 0.6 and 763 below 0.4. About 2,129 more are declined on the minimum area anyway.

## The rule (`auto_select_rule/1`)

It runs inside `write_run`'s transaction, after the new run and its regions are written. It applies only to runs with `publish=True` and `detector_key = 'bird'`; `publish=False` artifact runs are excluded. If the rule raises, the run write still commits and the rule's failure is logged.

1. If the image's active selection was written by `auto_select_rule` for an older run, revoke it (reason `superseded`) and continue. This keeps the rule's own selections on the current run; selection freshness is off, so nothing else does.
2. If the image has an active selection from any other selector, do nothing. Reason: `other_selection_active`.
3. If the run is not a v1 run (`detector_version` ends in `bird_detect_v1.pt`), record `not_v1`. v0 boxes are never promoted as they are (owner, #858 review, 2026-11-15).
4. If the run's status is `disabled` with `error_code = scene_route`, record `scene_route_skip`.
5. If the run's status is `no_detection`, or it has no rank-0 region, record `no_detection`.
6. If the rank-0 region's area fraction is below `species_min_area` (0.005, the existing runtime-rule value), record `below_min_area`.
7. If the rank-0 region's confidence is below **T** (D3), record `below_confidence`.
8. Otherwise call `select_region(..., selected_by="auto_select_rule/1:<rule sha>", evidence={…}, transaction=tx)`. The evidence holds the rule hash, run id, detector version and config hash, confidence, area and scene label. Any status other than `selected` is recorded as the reason.

Errors and retryable statuses (`terminal_error`, `detector_unavailable`) record nothing and leave the image for the next attempt.

## Acceptance criteria

- **AC-1** When a lane writes a current v1 bird run that passes the rule, the system shall create an active selection whose `selected_by` names the rule id and hash, with the evidence fields listed above, in the same transaction as the run.
- **AC-2** When the rule declines a run, the system shall write one row to `image_localization_selection_decisions` (run id, image id, rule sha, reason code, time).
- **AC-3** The system shall not revoke or replace an active selection written by any selector other than `auto_select_rule`.
- **AC-4** When a newer current run replaces the run behind an `auto_select_rule` selection, the system shall revoke that selection (`superseded`) and evaluate the new run.
- **AC-5** The system shall not select a region from a v0 run, or from a `publish=False` run.
- **AC-6** While `localization.auto_selection.enabled` is off (the default), the system shall write neither selections nor decision rows.
- **AC-7** These call sites shall reach the rule only through `write_run`, with no lane-specific call: the WebUI/pipeline runner (`modules/localization_runner.py`), the repair lane (`modules/localization_lane.py`, through the runner), the keypoint backfill (`scripts/backfill_region_keypoints.py`), and the maintenance scripts (`scripts/maintenance/redetect_v0_pilot_810.py`, `scripts/maintenance/shadow_rescan_bird_v1_misses.py`).
- **AC-8** A dry-run command shall report, for current v1 runs without a selection, how many the rule would select and the count per reason code, without writing.
- **AC-9** One command shall revoke every selection with a given `selected_by`, restoring the previous `bird_bbox`, with a dry-run mode that prints the count.
- **AC-10** If the rule raises, `write_run` shall still commit the run, and the error shall be logged.
- **AC-11** Tests shall cover each rule branch, AC-3 to AC-6, AC-10, and the `write_run` hook used by every call site in AC-7. The decisions table comes with its DDL in `modules/db_schema/`, an Alembic migration in `migrations/versions/` and an entry in `POSTGRES_APP_TABLES`.

## Decisions

The owner delegated D1–D6 on 2026-11-20 to sub-agent research (an Opus agent for code and data, a Fable agent for method), with a final call by Jev (`jev-1.14.0`). The receipt is `.agent/scratch/867-spec/jev-decision-867-d1-d6.json`.

| # | Decision | Outcome | Basis |
|---|---|---|---|
| D1 | Gate before enabling | **No new pre-gate** (Jev 0.89). The Evidence section is the one-time calibration; AC-9 is the rollback | A parity gate on v1 runs compares one detector with itself (600/600, IoU 0.999) and would be an eighth round of a metric the owner set aside |
| D2 | Where the rule runs | **Standalone in `write_run`** (Jev 0.88) | The authority path needs the judge and 130-per-band qualification R6 rules out, hardcodes a 0.70 cut under a frozen hash, and its active mode would change species predicates for the 4,667 existing selections |
| D3 | Confidence threshold T | **Owner's.** Jev deferred (0.70 on defer; T = 0.6 got 0.22) | T changes no species outcome while the embedded detector is on. Below 0.6, 9/17 v1 boxes were wrong, but the bins came after the data. Options: no extra step (0.25 plus minimum area), 0.6 labelled as chosen after the data and re-checked on fresh labels before #638, or another value |
| D4 | Where reason codes live | **A new `image_localization_selection_decisions` table** with a migration (Jev 0.97) | No existing table fits: the authority evaluation table rejects other rule kinds, and `error_code` and `skip_reason` already mean detection |
| D5 | Backfill of existing v1 runs | **AC-8 dry run first; the write needs a separate owner go** (Jev 0.73) | The write rewrites `bird_bbox` for thousands of images, and the older pool has the thinnest evidence (54 pairs) |
| D6 | Order against #810 | **Finish #810, then enable and backfill in one pass** (Jev 0.88) | #810's `rollback.sql` only makes v0 current again. A selection written mid-run would stay on a demoted run after a rollback |

## Out of scope

- Routing by subject class and non-bird animals (Phase D, #811, #849).
- Keypoints, masks and box refinement (#715 is closed).
- Scoring and culling as consumers: they stay full-frame (rollout decision summary).
- Retiring the embedded detector (#638). This spec only removes one of its blockers; what happens to declined frames after #638 is part of that work.
- Selections from other selectors, and selection freshness in the authority subsystem.
