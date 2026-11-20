---
type: Feature Spec
title: "Spec 09: automatic selection for new bird runs"
description: A versioned rule that turns each new detected v1 bird run into an active selection, or records why not, in every lane, so species reads one box path without a manual promotion step.
resource: docs/specs/pipeline-streamlining/09-automatic-selection.md
tags: [specs, localization, selection, species, automation]
timestamp: 2026-11-20T00:00:00Z
okf_version: 0.2
status: draft
---

# Spec 09: automatic selection for new bird runs

**Issue:** #867 · **Hub:** [INDEX.md](INDEX.md) · **Epic:** #345 · **Depends on:** #810 (v0 re-detection), #858, #869

**Status: draft.** The open decisions in [§ Owner decisions](#owner-decisions) are the owner's. No default in this spec is the owner's value, and nothing ships until those decisions are recorded.

## Summary

This is acceptance criterion AC5 of the [localization reassessment](../../planning/localization-reassessment-2026-11-12.md), which comes from requirement R6: new bird-tagged images get a selection with no manual tranche or manifest step.

Today a selection exists only where a one-off promotion wrote it (#472, #694, the v1 re-gate rules). New images get a current `bird` run but no selection, so species keeps using the embedded detector for them, and #638 can't retire it.

This spec adds one versioned rule. It runs where every lane already persists a run, `write_run` in `modules/localization.py`. For each new current v1 run, the rule either selects the rank-0 region through the existing `select_region` or records a reason code. No judge, Jev call or human label runs in production (R6).

## Consumer outcome and what stays blocked (#859)

- **Consumer:** species. It is the only live reader of selections (#857, D1). `read_bird_bbox` returns the active selection first, then the legacy payload, then the column.
- **Outcome protected:** the species stored outcome (top-1 label, or abstention) for images that receive an automatic selection. A framing or box-tightness standard is not the gate: no live reader is sensitive to it (#857, F2).
- **If the gate fails:** the rule stays off. Selections already written stay as they are, the embedded detector stays on, and #638 stays blocked.
- **Iteration count:** this is the first gate for automatic selection. The earlier #694 rounds gated a framing standard for a different purpose. They are not reused here, and their sample is excluded.
- **Policy owner:** the gate, T and the rule's place (D1 to D3) are the owner's. Values in this draft are candidates.
- **Resolution:** the AC-8 report gives counts with Wilson 95% intervals, and the owner-reviewed disagreements, not just pass or fail.

## Current state (2026-11-20, local database)

| Bird-tagged images (keyword `bird`/`birds`) | Images | With an active selection |
|---|---:|---:|
| Current v1 run, `detected` | 23,718 | 4,628 |
| Current v0 run, `detected` (#810 is re-detecting these) | 10,140 | 0 |
| Current v1 run, `no_detection` | 5,173 | 0 |
| Current v1 run, `disabled` (scene-route skip) | 163 | 0 |
| **Total** | **39,194** | **4,628** |

The active selections come from `v1_regate_rule/3` (4,375), `v1_regate_rule/4` (273) and `bbox_review_20261023/jev` (19). Every bird-tagged image has a scene label (#809).

The localization authority (`modules/localization_active.py`, `localization_authority_*`) is in `shadow` mode with selection freshness off. Its approval path (`validate_qualification`) requires three distinct calibrated judges and a registered 130-per-band validation. That is the #694 gate, which the reassessment closed (F2, F3) and which R6 rules out as a production step. See D2.

## Proposed rule (`auto_select_rule/1`, candidate values)

For a run that `write_run` has just made current:

1. If the image already has an active selection, from any selector, do nothing. Reason: `other_selection_active`. The rule never replaces a selection.
2. If the run is not a v1 run (`detector_version` ends in `bird_detect_v1.pt`), record `not_v1`. v0 boxes are never promoted as they are (owner, #858 review, 2026-11-15); #810 re-detects them first.
3. If the run's status is `disabled` with `error_code = scene_route`, record `scene_route_skip`.
4. If the run's status is `no_detection`, or the run has no rank-0 region, record `no_detection`. Species abstains with `no_bird_box` (#869).
5. If the rank-0 region's area fraction is below `species_min_area` (0.005, the value in the existing runtime rule), record `below_min_area`.
6. If the rank-0 region's confidence is below **T** (D3), record `below_confidence`.
7. Otherwise call `select_region(image_id, region_id, selected_by="auto_select_rule/1:<rule sha>", evidence={…})`. The evidence holds the rule hash, run id, detector version and config hash, confidence, area and scene label. Any status other than `selected` is recorded as the reason.

Errors and retryable statuses (`terminal_error`, `detector_unavailable`) record nothing and leave the image for the next attempt.

## Acceptance criteria

- **AC-1** When a lane writes a current v1 bird run that passes the rule, the system shall create an active selection whose `selected_by` names the rule id and hash, with the evidence fields listed above.
- **AC-2** When the rule declines a run, the system shall record one reason code from the list above for that image and run, in the store D4 decides.
- **AC-3** The system shall not revoke or replace an active selection made by any other selector.
- **AC-4** The system shall not select a region from a v0 run.
- **AC-5** While `localization.auto_selection.enabled` is off (the default), the system shall write neither selections nor reason codes.
- **AC-6** Every production lane that writes runs (WebUI/pipeline runner, repair lane, keypoint backfill, maintenance scripts) shall reach the rule through `write_run`, with no lane-specific call.
- **AC-7** A dry-run command shall report, for the existing current v1 runs without a selection (19,090 today), how many the rule would select and the count per reason code, without writing.
- **AC-8** Before enabling, a species outcome report on a fresh sample shall meet the gate the owner sets in D1. The sample is current v1 `detected` frames without a selection, capped at 5 per shoot, and it compares the selection arm (`region:box`) with the current embedded path, using `scripts/research/species_parity_858.py`.
- **AC-9** Tests shall cover each rule branch, the no-replacement rule (AC-3), the v0 refusal (AC-4), the off switch (AC-5), and the `write_run` hook used by every lane (AC-6).

## Owner decisions

| # | Decision | Options | Note |
|---|---|---|---|
| D1 | The gate in AC-8 | (a) species top-1 agreement ≥ X% between the two arms; (b) on owner-reviewed disagreements, the selection arm is not worse more often than the embedded arm; (c) no extra gate, relying on the #858 review and the #879 comparison | On 2026-11-15 the owner said parity alone is not the criterion |
| D2 | Where the rule runs | (a) a standalone rule calling `select_region`, like the `v1_regate_rule` selections; (b) the authority's active mode, with its qualification contract changed to a species-outcome receipt | Option (b) means replacing the judge and 130-per-band requirements in `validate_qualification` |
| D3 | Confidence threshold T | Any value from the v1 operating point (`min_confidence`) upward | A higher T selects fewer frames, and species keeps the embedded path for the rest |
| D4 | Where reason codes live | (a) the selection evidence plus a small decisions table; (b) the authority observation tables | Needed for AC-2 and for reporting |
| D5 | Backfill of existing v1 runs without a selection | Run AC-7 as a dry run first; the write is a separate go | 19,090 images today, more after #810 |
| D6 | When v0 frames qualify | After #810 finishes, the re-detected frames are new v1 runs, so the rule covers them through `write_run` if it is enabled first; otherwise the D5 backfill picks them up | The order is the owner's |

## Out of scope

- Routing by subject class and non-bird animals (Phase D, #811, #849).
- Keypoints, masks and box refinement (#715 is closed).
- Scoring and culling as consumers: they stay full-frame (rollout decision summary).
- Retiring the embedded detector (#638). This spec only removes one of its blockers.
