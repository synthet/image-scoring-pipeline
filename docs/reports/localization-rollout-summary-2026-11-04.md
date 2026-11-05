---
type: Report
title: Localization Rollout Summary (2026-11-04)
description: "Summary of the early-localization rollout: intentions, goal, background, current status, specs and features, and open issues, defects and blockers as of 2026-11-04."
resource: reports/localization-rollout-summary-2026-11-04.md
tags: [localization, rollout, bird-detection, bioclip, authority, summary]
timestamp: 2026-11-05T01:38:00Z
okf_version: 0.2
---

# Localization rollout summary (2026-11-04)

Replaces [the 2026-10-22 summary](localization-rollout-summary-2026-10-22.md) as the latest overview.
The design and stage history stay in [localization-rollout.md](../architecture/pipeline/localization-rollout.md).
The current plan is [localization-rollout-plan-2026-11-04.md](../planning/localization-rollout-plan-2026-11-04.md), and the diagrams are in [localization-diagrams.md](../architecture/pipeline/localization-diagrams.md).

**Sources.** Counts marked *live* come from read-only database queries at 2026-11-05 01:38 UTC. Older figures carry their date and come from the linked report or issue.

## In short

**The rollout is partly in production, not finished.**

- **Live:** localization is a real pipeline phase, and BioCLIP reads selected bird regions.
- **Not live:** automatic promotion is in `shadow` with no approved policy, and `images.bird_bbox` is still the production read.
- **Coverage:** 4,665 images have an active selection, about 9% of the 52,135 with a detected bird (*live*).
- **Main blocker:** #694 cannot promote more boxes until two more vision judges qualify.

## Goal

Make bird boxes, and later other object boxes, a first-class pipeline artifact produced right after metadata. Downstream phases then use one recorded, revocable region decision, not a JSON column written as a side effect of species classification.

The end state has three parts:

1. Selections cover the bird images that matter.
2. BioCLIP's embedded detector can be retired.
3. Normalized regions replace `images.bird_bbox` as the read path. Physically dropping the column is out of scope.

## Intentions

These rules shaped every stage and still apply:

- **Additive and reversible.** Each stage has its own flag, exit gate and rollback.
- **Shadow first.** New output earns production use through a gate, not by existing.
- **Selections are the authority.** A current shadow run is not a production decision.
- **Promotion is by gated rule, not by detector.** A rule must pass on a fresh sample.
- **Full-frame semantics stay.** Scoring and culling do not change until a gate says so.
- **Regions are preferred inputs, not hard prerequisites.** Downstream phases can still run without them.
- **Deterministic checks decide.** Jev and agent judges advise; backups, receipts and gates control data changes.
- **Calibration and test sets are not for tuning.** Thresholds are set before results are read.

## Background

Boxes began as a side effect: the species classifier wrote `images.bird_bbox`, so nothing recorded which detector produced a box or whether it could be trusted. The rollout started as eight stages under epic #345, closed 2026-10-04.

| Date | Milestone |
|---|---|
| 2026-09-22 | Control plane and normalized persistence land (#346, #370) |
| 2026-09-27 | Legacy import: 76,475 current runs |
| 2026-10-01 | First v1 promotion gate **fails** (#469) |
| 2026-10-03 | Re-gated `v1_regate_rule/3` passes; 4,401 selections promoted (#472) |
| 2026-10-15 | **Stage 5 live:** region BioCLIP on; 274 small boxes promoted geometry-only; cascade enabled in shadow |
| 2026-10-22 | v9.2.0 released; compatibility view applied (migration 0043) |
| 2026-10-23 | `read_normalized_first` rollback drill passes; flag stays off |
| 2026-10-25 | #694 replaces #683: coverage is a promotion gap, not a detection gap |
| 2026-10-26 | R2 rule frozen; calibration stops with one qualified judge |
| 2026-10-29 to 31 | Authority runtime merged, dormant by default (#697 to #710) |
| 2026-11-01 | Production migrated to 0048; authority set to `shadow` |
| 2026-11-03 | Spec 08 written; #802 and #803 merged; WebUI stops at 06:00 UTC |
| 2026-11-04 | Spec 08 first shadow run starts; full-size AC-9 passes |

## Current status

### Production state (*live*)

| Item | State |
|---|---|
| Schema revision | `0048` |
| Authority mode | `shadow`; 0 policy approvals; selection freshness off |
| Active selections | 4,665: 4,372 `v1_regate_rule/3`, 274 `v1_regate_rule/4`, 19 from the 2026-10-23 box review |
| Revoked selection rows | 847 |
| Images with a current detected bird run | 52,135 |
| `bird_species.use_regions` | On in `config.json` |
| `localization.read_normalized_first` | Not set in `config.json`, so default false |
| `bird_species.embedded_detector` | Not set in `config.json`, so default true |
| WebUI | **Stopped** since 2026-11-03 06:00 UTC |
| Reservations | 0 imported; 1 policy registered |

### Stages

| # | Stage | Status | Still open |
|---|---|---|---|
| 1 | Control plane | **Done** | Phase edges #681, #682 |
| 2 | Normalized persistence | **Done** | Masks and a second keypoint pass (#426) |
| 3 | Rendition and crops | **Code complete** | Decode once for every phase (#406) |
| 4 | Shadow localization | **Live lane observed; cascade in shadow** | Production retry timing unobserved as of 2026-10-26; cascade adoption needs its own gate |
| 5 | BioCLIP on regions | **Live** for large and medium | Small-crop species (#610); species list (#422); multi-region |
| 6 | Crop and fusion | **Not started**; research epic #645 | Labelled bursts (#415), storage (#409), evidence (#423) |
| 7 | Repair and backfill | **Partly done** | Retry timing; crop backfill after #409 |
| 8 | Retire `bird_bbox` | **View deployed, flag off** | Compatibility release, selection coverage (#638) |

### Promotion gate (#694)

The cohort has 30,046 runs, with a fresh sample of 390 frames frozen on 2026-10-26. The frozen R2 rule needs confidence of at least 0.70 and at most three regions; small boxes stay geometry-only.

Three judges must each score at least 18/20 on calibration. Antigravity scored 19/20; Codex and Claude scored 17/20. The fresh sample cannot be judged until that requirement is met.

The shadow scan records what the rule would do, without changing production. It stopped at cursor 239,048 of 241,459, the highest run that isn't `bird_agreement` (*live*):

| Outcome | Reason | Evaluations |
|---|---|---:|
| abstain | `outside_original_population` | 45,830 |
| abstain | `unknown_producer_scope` | 21,032 |
| **accept** | `r2_eligible` | **6,504** |
| abstain | `outside_artifact_scope` | 4,347 |
| reject | `confidence_below_threshold` | 2,144 |
| reject | `region_count_outside_rule` | 523 |

Of the 9,171 runs the rule actually judged, 71% were accepted. These are proposals, not selections.

### Bird box agreement (#780, spec 08)

This is a shadow measurement, separate from the #694 gate. `bird_detect_v1` boxes things that are not birds, and those boxes pick up false eyes. Spec 08 asks RTMDet to confirm each region on its padded crop.

The benchmark (image-scoring-model #41) supports a light rule: detector at least 0.25, RTMDet agreement at least 0.10, IoU at least 0.3.

| No-bird frames with a false eye | Today | Per-crop check |
|---|---:|---:|
| Calibration | 0.56 | 0.26 |
| Test | 0.19 | 0.10 |
| Confirmation | 0.43 | 0.14 |

The test-set improvement alone is not significant. Eyes within 5% did not fall on any set, and one bird was lost on confirmation (0.72 to 0.70). A stricter rule was rejected because birds found fell from 0.72 to 0.44.

| Check | Result |
|---|---|
| AC-9 at 2048 px | 134 of 134 regions matched (#802) |
| AC-9 at full size | 129 of 131 scored regions matched (98.5%); worst case 129 of 134 (96.3%); bar is 95% |
| First run target | 33 dev and pilot shoots, 13,744 detected frames |
| Progress (*live*, still running) | 2,065 runs across 25 shoots; 2,551 regions; 427 below the limit; 0 current runs; 2 retryable |

The live counts include `Z6ii/28-400mm/2026/2026-02-21`, which is outside the first-run set and stays out of the review sample.

A promotion spec is justified only if false-eye regions fall by at least a third and fewer than 2% of confirmed birds are lost. That is judged on a fixed sample of 100 regions below the limit and 100 at or above it.

## Specs and features

### Specs

Spec `status:` fields lag behind delivery, so this table shows the issue state as well.

| Spec | Issue | Issue state | Notes |
|---|---|---|---|
| [01 Decode-once rendition](../specs/pipeline-streamlining/01-rendition.md) | #406 | Open | Cache and pruner slice landed (#446) |
| [02 Phase graph](../specs/pipeline-streamlining/02-phase-graph.md) | #407 | Closed | Follow-ups #681, #682 |
| [03 Detector cascade](../specs/pipeline-streamlining/03-detector-cascade.md) | #408 | Closed | Runs in shadow; adoption not decided |
| [04 Subject-aware scoring](../specs/pipeline-streamlining/04-subject-aware-scoring.md) | #409 | Open | Needs labelled bursts |
| [05 Scene route](../specs/pipeline-streamlining/05-scene-route.md) | #412 | Closed | SigLIP2 route at p ≥ 0.065 |
| [06 Species beyond birds](../specs/pipeline-streamlining/06-multi-taxon-species.md) | #413 | Open | Benchmark first |
| [07 Blockers and decisions](../specs/pipeline-streamlining/07-blockers-and-decisions.md) | #417 | Closed | Register; dated snapshot |
| [08 Bird box agreement](../specs/pipeline-streamlining/08-bird-box-agreement.md) | #780 | Open | First shadow run in progress; [plan](../planning/bird-box-agreement-plan.md) |

### Delivered features

| Feature | State | Reference |
|---|---|---|
| Normalized runs and regions | Live | [DB_SCHEMA](../technical/DB_SCHEMA.md) |
| Selection ledger | Live; revocable | `image_localization_selections` |
| Automatic lane with bounded repair | Live when WebUI runs | Stage 4 and 7 history |
| Scene route | Live | #412 |
| Region BioCLIP | Live | [Stage 5 activation](localization-stage5-activation-2026-10-15.md) |
| Compatibility reader and view | Deployed, flag off | [NORMALIZED_BBOX_COMPATIBILITY](../technical/NORMALIZED_BBOX_COMPATIBILITY.md) |
| Gallery normalized consumer | Merged, default off | gallery #185 |
| Shadow authority worker | Live when WebUI runs | [LOCALIZATION_AUTHORITY_SHADOW](../technical/LOCALIZATION_AUTHORITY_SHADOW.md) |
| Active authority and freshness | Merged, dormant | [LOCALIZATION_AUTHORITY](../technical/LOCALIZATION_AUTHORITY.md) |
| Bounded idle recovery and canaries | Merged | #703, #706 |
| Species convergence with provenance | Merged | #702 |
| Bird box agreement | Shadow; `localization.agreement.enabled` false | #802, #803 |

## Issues, defects and blockers

### Blockers

| Blocker | Stops | Issue | Clears when |
|---|---|---|---|
| Only 1 of 3 judges qualified | Judging the fresh sample, then any promotion or activation | #694 | Two more judges reach 18/20 on the unchanged threshold |
| Selection coverage about 9% | Retiring BioCLIP's detector; Stage 8 | #638, #694 | Selections cover the bird-tagged images |
| Full compatibility release incomplete | `read_normalized_first`; Stage 8 | #638 | Release observation finishes |
| About 300 labelled bursts missing | Stage 6 and subject-aware scores | #415 | Labels exist |
| Spec 08 review not done | Any agreement promotion spec | #780 | First run ends, sample drawn, owner judges 200 regions |

### Defects and risks

| Item | Effect | Tracking |
|---|---|---|
| **WebUI stopped.** It ran exactly 5h 00m 01s, exit 137, not out of memory. `unless-stopped` did not revive it, which suggests a manual or scripted stop. Cause not found. | Automatic lane and shadow scan do not run; new images are not localized | None found |
| **802 images have more than one current detected run**, all from the Oct 16 to 28 cascade pilot (*live*). Keep-one expects exactly one. | Those frames could fail keep-one after a snapshot refresh | #627 |
| **R2 may not close the coverage gap.** It accepted 6,504 runs, against 28,475 unselected bird-tagged images counted on 2026-10-25. | Passing #694 may still leave coverage short of detector removal | #694, #810 |
| **Residual false eyes.** 0.10 to 0.26 of no-bird frames keep a false eye under the per-crop check. | The check reduces the problem but does not remove it | #780 |
| **Agreement speed unexplained.** Full shoots ran at 0.9 and 2.0 s/image; the 20-image dry run took 8.6 s/image. RTMDet runs on CPU in the container. | Cost of any wider run is uncertain | #780 |
| **Full-size scoring leans permissive.** Both AC-9 differences moved from fail to pass; 3 regions were skipped on orientation (`b0020`, `b0094`), cause not examined. | Slightly more false boxes could pass near the limit | #780 |
| **Parity script not committed.** A hook blocked the commit with `sensitive_path_or_secret`; the trigger is unconfirmed. | AC-9 full-size result cannot be reproduced from the repo yet | #780 |
| **`image-scoring-ui` checkout emptied** on 2026-11-04 by a worktree removal that followed a `node_modules` link. Restored from GitHub the same day; any unpushed local work is unknown. | Any worktree with `frontend/node_modules` still links to it, so a removal can repeat this | None found |
| **Small-crop species failed** its gate (0.8123 < 0.85). | Small selections stay geometry-only | #610 |
| **Species enters through the `birds` keyword** (decision G-2). | Detector-positive images without it get no region species | Rollout open questions |
| **6 held selection disagreements**, kept after the 2026-10-25 recount. | They serve the selection's box when the flag is on | #638 |
| **Stored-box parity is weak.** A 40-image probe on 2026-10-24 matched top-1 species on 37 but the box on only 9. | `embedded_detector` stays true | #638 |
| **Stopped 200-image cascade pilot** has no recorded recovery policy. | Must be settled before any replay | Rollout "What is left" |
| **Retry timing unobserved** in production as of 2026-10-26; not rechecked here. | 1 min and 5 min schedule lacks live evidence | Rollout "What is left" |
| **Rollout state tracking.** #780 has no labels, and #694 still shows `stage:backlog` while work runs. | Board does not show what is active | #780, #694 |

### Open work by priority

| Issue | Priority | Summary |
|---|---|---|
| #694 | p2 | Promotion gate and tranches |
| #627 | p2 | Subject and head-evidence coverage |
| #422 | p2 | Species list gaps and abstention |
| #406 | p2 | Decode once |
| #409, #423, #645 | p2 | Subject-aware scoring and evidence |
| #638 | p3 | Stage 8 readiness |
| #610 | p3 | Small-crop species evaluation |
| #426 | p3 | Keypoint and mask providers |
| #681, #682 | p3 | Phase edge refinements |
| #780 | none set | Bird box agreement |
| #715 | none set | Mask box tightness research |

## What comes next

1. **Restore operations.** Find out why the WebUI stopped, then start it with `docker compose up -d webui` once no shoot is active. The scan can then finish. This is an owner decision.
2. **Finish spec 08's first run.** Draw the fixed sample only after the queue ends. The owner then judges it against the promotion bar.
3. **Unblock #694.** Qualify two more judges without changing the threshold, then judge the frozen fresh sample.
4. **Check R2's reach.** Compare its accepts with the unselected bird-tagged images once the scan finishes, and decide whether a further rule is needed.
5. **Resolve the 802 images** before enabling the cascade on keep-one shoots.

## Where to read more

- [Rollout design and history](../architecture/pipeline/localization-rollout.md)
- [Promotion gate, 2026-10-26](localization-promotion-gate-2026-10-26.md)
- [Stage 8 readiness, 2026-10-23](localization-stage8-readiness-2026-10-23.md)
- [Pipeline streamlining spec hub](../specs/pipeline-streamlining/INDEX.md)
