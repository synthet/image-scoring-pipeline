---
type: Report
title: Localization Stage 8 Readiness 2026-10-23
description: "#660 BioCLIP repair close-out, WebUI on v9.2.0, read_normalized_first rollback drill, the 43 legacy/view bbox disagreements, backfill reroute and what still gates #638."
resource: reports/localization-stage8-readiness-2026-10-23.md
tags: [localization, rollout, stage-8, bird-bbox, bioclip, rollback]
timestamp: 2026-10-23T21:30:00Z
okf_version: 0.2
---

# Localization Stage 8 readiness (2026-10-23)

Point-in-time record. The status of record stays in
[localization-rollout.md](../architecture/pipeline/localization-rollout.md). Receipts are local,
under `.agent/scratch/repair641-20261018-resumed/` (gitignored).

## #660 full-frame BioCLIP repair: complete

| Run | Window (UTC) | Result |
|---|---|---|
| `rebuild_resume_20261022.py` | 10-22 23:25 – 10-23 02:37 | Stopped by design: WebUI auto-drive queued jobs 7035–7036. +9,408 vectors (19,328 present). |
| `rebuild_resume_20261023.py` | 13:43 – 14:20 | Stopped by design on decode failures (71048, 71062). +2,470 (21,798 present). |
| `rebuild_resume_20261023b.py` | 16:38 – 19:09 | **Completed**, exit 0. +11,955; **33,753 / 33,753** present. Quality: 768-d, 0 invalid. |

- **Preservation checks.** Every stop and the final run reported `completed_existing_unchanged`,
  `untouched_rows_unchanged` and `protected_state_unchanged` true. Each resume was reconciled
  read-only first (`reconciliation-stopped-resume-20261023{,b}.json`, 10/10 and 12/12 checks).
- **Auto-drive jobs.** Jobs 7035–7039 wrote only non-target rows: 5 full-frame and 64 crop
  vectors, plus 158 localization runs for a new folder.
- **Backup.** A fresh verified backup was taken before the resumes:
  `image_scoring_20261023_083553.dump` (1.49 GB, full archive read, 8 critical tables).
- **Final space counts.** `bioclip_2_image` 74,129, `bioclip_2_crop` 4,093. The #641 invariant
  holds.
- **Excluded from the target: 71048, 71062, 71135.** Their originals
  (`Z8/180-600mm/2026/2026-04-09/DSC_0004/0017/0086.NEF`) are **zero-filled for their whole
  length**, with no data block left, so they can't be recovered from this disk. A header scan of
  every remaining source found no others. Their rows are unchanged and they have no full-frame
  vector. Deleting the records is a separate owner decision, as it was for the 8 missing
  originals.

## WebUI on v9.2.0 and #639

- **Startup.** WebUI started at 20:32 UTC on `master` (v9.2.0 plus docs). `init_db` waited about
  7 min on a lock held by a long external `psql` query, which finished on its own; then health
  returned 200.
- **#639 closed.** `GET /api/runs/drive/status` now reports `localization_lane` live:
  `hold_reason: null`, `restart_required: false`, `outage_streak: 0`. This is the #653
  diagnostic, option 2. A real outage hold still needs a restart, but it is now visible.

## `read_normalized_first` rollback drill: passed

`drill_read_normalized_first_20261023.py` ran against the running WebUI through
`GET /api/images/{id}`. The flag was turned on with `modules.config.save_config_value` and off by
restoring the original `config.json` bytes.

| Phase | Expected | Checked | Mismatches | Switch latency |
|---|---|---|---|---|
| off (baseline) | legacy column | 143 | 0 | — |
| on | compatibility projection | 143 | 0 | 0.04 s |
| off (rollback) | legacy column | 143 | 0 | 0.04 s |

- **Sample.** All 43 disagreements, 50 agreeing selected images and 50 agreeing unselected
  controls.
- **On.** Exactly 43 images changed what they served.
- **Off.** The flag was on for 12.6 s in total. `config.json` was restored byte-identical (sha
  checked), and no restart or detection rerun was needed.
- **Result.** This meets the Stage 8 precondition that normalized-first reads can be disabled
  independently.

## Legacy/view disagreements: 43, not 31

`audit_bbox_disagreements_20261023.py` compared `images.bird_bbox` with `image_bird_bbox_compat`
for every image (packet `bbox-disagreements-20261023.json`; overlays in
`disagreement-review-20261023/index.html`).

- **31 selected images.** The view serves the selection projection.
  - The two boxes share frame dimensions, so the difference is not a coordinate-space mismatch.
  - None are within 1 px. 13 have IoU ≥ 0.9, and two (207843, 207846) have IoU 0, meaning the
    boxes are on different birds.
  - The legacy box carries the higher confidence (about 0.79–0.94 against 0.57–0.70).
  - **This corrects the 2026-10-22 summary**, which said all 31 were "within one pixel of the
    selection projection".
  - An earlier comparison found that all 31 matched their projections in the October 5 backup.
    So a legacy writer most likely overwrote them before the #646 guard.
- **12 unselected images (new).** The view replays an imported `legacy_payload` (2026-09-27)
  that no longer matches the column.
  - Three are presence changes: the column holds `{"detected": false}` and the view would serve
    a box.
  - The others have IoU ≥ 0.74.
  - The legacy writer updates `bird_bbox` without touching `updated_at`, so these columns were
    probably rewritten after the import. This is not proven.
  - With the flag on, these images would serve the older imported value.

Which box is right is an owner decision, made per image from the overlay sheet. It has to happen
before the flag is left on. The drill doesn't depend on it.

## Writer reroute (#664)

`scripts/backfill_bird_bbox.py` now queues ID-scoped localization jobs. It no longer runs a
detector or writes `bird_bbox`. A production dry-run would queue 1,802 images and skip 92 that
already have a current run. The bird-tagged default finds 0 candidates.

## What still gates #638

1. **A full compatibility release.** v9.2.0 has been running since 2026-10-23 20:32 UTC. The
   precondition requires at least one complete release with no unresolved convergence
   regressions.
2. **BioCLIP's embedded detector stays for now.**
   - Of 38,419 bird-tagged images, only 4,642 have an active selection. The other ~33.8k get their
     species crop from the embedded detector.
   - Removing it now would move them to full-frame classification on their next classify.
   - It waits until normalized selections cover those images (Stage 5 exit and Stage 7
     relocalization), not only on the calendar.
3. **Owner review of the 43 disagreements** before `read_normalized_first` is left on.
4. **Owner decision on the three zero-filled originals.**
