---
type: Report
title: Localization Rollout Summary
description: "One-page summary of the eight-stage early-localization rollout: goal, timeline, stage status, gates, deployment and open work as of 2026-10-22."
resource: reports/localization-rollout-summary-2026-10-22.md
tags: [localization, rollout, bird-detection, bioclip, summary]
timestamp: 2026-10-23T00:30:00Z
okf_version: 0.2
---

# Localization rollout — project summary (2026-10-22)

The status of record is [localization-rollout.md](../architecture/pipeline/localization-rollout.md).
This page condenses it. Where they differ, the status of record wins.

## Goal

Make bird (and later other object) boxes a first-class, reusable pipeline artifact,
produced early, right after metadata, instead of a JSON column that the species
classifier writes as a side effect. Downstream phases then consume one recorded,
revocable region decision. Full-frame scoring and culling semantics must not change
until a gate says so.

The rollout was designed as eight additive, reversible stages under epic #345
(closed 2026-10-04; this page and the status of record replace its issue body).

## Outcome so far

- Localization is a real phase after `metadata`, with normalized persistence
  (`image_localization_runs`, `image_regions`) and a production **selection ledger**
  (`image_localization_selections`) that decides which region is authoritative.
- **4,675** active selections: 4,401 large/medium boxes (`v1_regate_rule/3`, owner
  gate) and 274 small geometry-only boxes (`v1_regate_rule/4`, agent-panel gate).
- **Region BioCLIP is live** since 2026-10-15: species reads the selected crop.
  Under the 379-name list, 4,029 of the 4,401 are labelled and 372 abstain.
- The automatic localization lane runs for new images while core work is idle,
  with bounded repair (3 attempts, 1 min / 5 min) and a scene route that skips
  detection on non-bird scenes.
- The legacy `images.bird_bbox` column is still the read path. For selected images
  it is a projection written only by the selection module. A default-off,
  selection-aware compatibility reader and SQL view (migration 0043) are released
  in v9.2.0, and the view is deployed.

## Timeline

| Date | Milestone |
|---|---|
| 2026-09-22 | Stage 1 control plane and Stage 2 normalized persistence land (#346, #370) |
| 2026-09-24 | Stage 4 slice 1: localization phase in shadow mode (#387) |
| 2026-09-27 | Legacy import: 76,475 current runs; eye keypoints in shadow |
| 2026-10-01 | First v1 promotion gate **fails** (#469) |
| 2026-10-03 | Re-gated rule/3 passes; 4,401 selections promoted (#472, #484) |
| 2026-10-07 | #368 deployed (migration 0040); bounded live batch verified |
| 2026-10-09 | Live automatic lane observed (jobs 6939, 6941); registration boundary fixed (#585, 0041) |
| 2026-10-12 | Agent-panel gates: large/medium species pass; small-crop species fails (0.8123 < 0.85) |
| 2026-10-15 | **Stage 5 live** (#592, #593); 274 small selections promoted geometry-only; cascade enabled (#408) |
| 2026-10-16 | 379-name species relabel (#619); live cascade runs observed |
| 2026-10-17 | Upright-input re-tag complete (#418); BioCLIP crop/full-frame spaces separated (#641, #643, migration 0042) |
| 2026-10-18 | Timing baseline measured (#416, still open) |
| 2026-10-19 | 4,029 crop vectors moved; 33,764 mixed full-frame vectors deleted (#641 repair) |
| 2026-10-20 | Rebuild pilot passes; Stage 8 readiness audit finds the dormant reader unsafe |
| 2026-10-21 | Selection-ownership guard for legacy bbox writes (#646, PR #647) |
| 2026-10-22 | v9.1.2 and v9.2.0 released; selection-aware reader + view 0043 (#652) and #639 diagnostics (#653) merged; 0043 deployed; 8 missing-original records removed; #641 repair resumed; status refreshed (#655) |

## Stage status

| # | Stage | Status | Main open items |
|---|---|---|---|
| 1 | Control plane | **Done** | #407 attempt-before edge, burst/picks split |
| 2 | Normalized persistence | **Done** | Masks and a second keypoint pass (#426) |
| 3 | Rendition and crops | **Code complete** | Decode-once for every phase (#406) |
| 4 | Shadow localization | **Live lane observed; cascade enabled as shadow** | Production retry timing unobserved; restart-only outage hold (#639) |
| 5 | BioCLIP on regions | **Live** (large/medium) | Small-crop species (#610); #422 list gaps; #641 vector repair |
| 6 | Crop / fusion | **Not started**; moved to research epic #645 | #415 labelled bursts, #409 storage, #423 evidence |
| 7 | Repair and backfill | **Partly done** | Retry timing; retire/reroute `backfill_bird_bbox.py`; crop backfill after #409 |
| 8 | Retire `bird_bbox` | **Compatibility view deployed (0043); flag off** | Gallery consumer delivery, rollback drill, 31 legacy/selection disagreements (#638) |

## Gates and decisions that shaped the rollout

- **Promotion is by gated rule, not by detector.** The first v1 gate failed
  (Wilson lower bound 0.78 < 0.90). Re-gating with the SigLIP2 scene route passed on
  large and medium boxes; the small stratum stayed in shadow until a separate
  geometry-only gate.
- **Small boxes feed geometry, not species.** Selections under 0.005 normalized area
  are excluded from region species until new pre-registered evidence exists (#610).
- **Selections are the authority**, not "current" shadow runs. The Stage 8 audit
  showed the original reader would have changed 4,646 images' geometry, so it was
  rewritten to follow selections before any activation.
- **Embedding spaces stay separate.** Crop and full-frame BioCLIP vectors must never
  share `bioclip_2_image` (#641). The historical mix is being repaired under owner
  approval, one confirmed step at a time.
- **Shadow first, flags off.** `localization.read_normalized_first` and the gallery
  consumer switch both remain off; each activation needs its own gate and rollback.
- **Jev (TypeSafe System One) advises, deterministic checks decide.** It ranked
  design alternatives and triaged delivery; backups, receipts and preservation
  checksums gated every data change.

## Deployment and repair state (2026-10-22)

- Released: **v9.1.2** (#648, includes #646) and **v9.2.0** (#659: #651, #652, #653,
  #654).
- Production database: migration **0043** applied at 23:13 UTC after a verified
  backup (`image_scoring_20261022_180151.dump`, full archive read). The installed
  `image_bird_bbox_compat` view matched the Python reader on 5,137 images (all 4,675
  selections, 449 unselected controls, imported samples) in 0.2 s; the 31 known
  legacy/selection disagreements remain. The reader flag and gallery switch stay off.
- #641 full-frame repair (tracked in #660, since #641 itself is closed): owner approved
  the resume on 2026-10-22. It started at 23:25 UTC over the 23,836 remaining images
  (33,756 targets) with a 14-hour cap and hourly preservation checks; at 00:14 UTC it
  had rebuilt 2,704 at about 0.93 images/s. Its baselines were captured at launch, so
  the 28 culling-only changes found on 2026-10-20 are preserved, not reverted.
- **The automatic lane is idle.** WebUI stays stopped until the repair finishes, so new
  images are not localized until it starts on v9.2.0. The #653 hold field reaches a
  running service only then.
- Gallery: the normalized consumer is implemented and verified locally only.

## What is left

1. Let the #641 repair finish (`rebuild-resume-20261022-receipt.json` reaches
   `completed`), then start WebUI on v9.2.0 with `docker compose up -d webui`.
2. Stage 8 (#638): commit the gallery consumer (default off), run a compatibility
   release, exercise rollback of `read_normalized_first`, review the 31
   disagreements, then retire or reroute `scripts/backfill_bird_bbox.py`. Physical
   column removal is out of scope. The 31 are already characterized: all held their
   legacy values in the October 10 backup, all are within one pixel of the selection
   projection, and 29 match native detector geometry exactly. The writer and which
   box is better are unproven; review them before any flag flip, not before the repair.
3. Stage 4/7: observe production retry timing; fix the restart-only hold (#639).
   Write a recovery policy for the stopped 200-image cascade pilot (38 replayed;
   four source identities changed) before any replay. Shadow cascade stays enabled;
   consumer adoption waits.
4. Stage 5 exit gate is still open: species enters through the `birds` keyword
   (decision G-2), so detector-positive images without it get no region species;
   multi-region and relocalization of keyword-positive misses are not built; the
   promotions used agent-panel labels. New small-crop evidence (#610); species list
   work (#422, #413).
5. Stage 6 research (#645): labelled bursts (#415), crop-score storage (#409),
   evidence bands (#423).
6. Timing baseline review (#416, measured 2026-10-18; the GitHub issue is not yet
   updated) before revisiting the 2048 px threshold.

## Documentation notes

#661 updated the status of record (deployment, current "What is left" order, timing
blocker, `status`) and the architecture indexes. Epic #345's issue body still holds the
September text. Older dated paragraphs on the status page (for example 31,764
remaining, WebUI restored) describe their own dates, not the current state.

## Where to read more

- Status of record and design: [localization-rollout.md](../architecture/pipeline/localization-rollout.md)
- Compatibility contract: [NORMALIZED_BBOX_COMPATIBILITY.md](../technical/NORMALIZED_BBOX_COMPATIBILITY.md)
- Stage 5 activation: [localization-stage5-activation-2026-10-15.md](localization-stage5-activation-2026-10-15.md)
- Latest continuation: [localization-continuation-2026-10-19.md](localization-continuation-2026-10-19.md)
- Timing baseline: [timing-baseline-2026-10-18.md](timing-baseline-2026-10-18.md)
