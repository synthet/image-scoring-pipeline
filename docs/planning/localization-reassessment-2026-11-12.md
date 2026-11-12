---
type: Report
title: Localization reassessment (2026-11-12)
description: A step back over the localization track after #694 promoted nothing. It restores the original goal, sets requirements and acceptance criteria, lists where the work drifted (with evidence), and holds the owner's open decisions.
resource: planning/localization-reassessment-2026-11-12.md
tags: [planning, localization, reassessment, requirements, decision-register, drift]
timestamp: 2026-11-12T00:00:00Z
okf_version: 0.2
status: proposed
---

# Localization reassessment (2026-11-12)

Tracking issue: [#856](https://github.com/synthet/image-scoring-pipeline/issues/856). It reviews [epic #345](https://github.com/synthet/image-scoring-pipeline/issues/345), the [rollout plan](localization-rollout-plan-2026-11-04.md), the [#694 owner validation](../reports/localization-owner-validation-694-2026-11-11.md), the commits since 2026-10-01, and the session transcripts from 2026-10-31 to 2026-11-11.

**Nothing here is an owner decision.** Every item in the [decision register](#5-owner-decision-register) is open. A recommendation is only a recommendation, and it stays labelled as one.

## In short

- **The drift is in one track.** From 10-25 to 11-11, the #694 promotion gate took 57 localization commits, about 3.8k lines of gate and judge tooling, and 1.7 GB of `.agent/scratch/promotion-694/`. It ran four preregistrations or amendments on one 390-frame sample and promoted **0** boxes.
  - The other recent work shipped concrete fixes and shows no drift: Sync, the scene route #809, the remote GPU runner, the gallery and the agent-flow rollout.
- **The gate measured something its consumer doesn't use.** It graded human framing: feet, tail and bill inside, and not too loose. The only live reader of selections is BioCLIP species, which classifies a *padded* crop. The detector the gate was meant to replace is the *same* `BirdDetector` with the same config. Promoting these runs would most likely hand species the crops it already gets today ([F2](#f2-the-gate-measured-what-its-consumer-does-not-use)).
- **#851 can never unblock.** It waits for near-dupe archive batch 2 to finish. That batch was withdrawn and restored on 11-11 ([F4](#f4-851-waits-on-a-condition-that-cannot-happen)).
- **The useful signal got buried.** Large boxes nearly passed (121/130). Medium and small failed on *clipping*, which calls for a box-refinement fix, not another gate ([F6](#f6-a-real-engineering-signal-was-buried)).
- **Recommended direction:**
  - Close the #694 gate as failed and recorded.
  - Replace the framing gate with a consumer-fit check: [#857](https://github.com/synthet/image-scoring-pipeline/issues/857) inventory, then [#858](https://github.com/synthet/image-scoring-pipeline/issues/858) species parity.
  - Unblock the real automation work (Phases B and D) and the p1 user bugs.
  - The owner decides all of this (D1–D6).

## 1. The goal, restored from its sources

| Source | What it says |
|---|---|
| Epic [#345](https://github.com/synthet/image-scoring-pipeline/issues/345) (2026-09-02) | Make bird boxes a first-class, reusable artifact. Today YOLO runs inside BioCLIP, after keywords, "too late for scoring, culling, or keyword inference to reuse it". Only one box survives, and `bird_bbox` has no provenance |
| [Rollout design](../architecture/pipeline/localization-rollout.md), decision summary | Regions are "preferred inputs, not hard prerequisites". "Keep culling and the production IQA/aesthetic result full-frame." "Let BioCLIP consume bird regions first." Other consumers get crops "only behind shadow flags and benchmark gates" |
| North star (owner, 2026-11-04), [rollout plan §1](localization-rollout-plan-2026-11-04.md#1-north-star-and-the-production-rule) | A fully automated workflow: detect scene/objects → route by subject type → boxes/masks/keypoints → scoring · culling · keywords · species. LLM judges and human labels **only tune and calibrate**, once. They are never a production step |
| [#638](https://github.com/synthet/image-scoring-pipeline/issues/638) (Stage 8) | Retire BioCLIP's embedded detector once selection coverage allows, through `bird_species.embedded_detector=false` |
| [#694](https://github.com/synthet/image-scoring-pipeline/issues/694) (2026-10-25) | Promote the 28,475 unselected YOLO `bird_detect_v1` runs to selections, because species reads only active selections. Its four ACs: freeze the rule; report the gate; on a pass, apply in tranches; on a fail, record it and the next rule. **The first, second and fourth are met. The third doesn't apply** |

The **end** is an unattended pipeline in which every eligible image gets a scene label, a route, regions with provenance, and consumers that use those regions where they measurably help. #694 was **one means**: a coverage step for one consumer (species), on the path to deleting one code path (the embedded detector).

## 2. Requirements and acceptance criteria

These come from the sources above. Thresholds marked _owner_ are open, and a default is never the owner's value.

| # | Requirement | Source |
|---|---|---|
| R1 | Every eligible image gets a scene label and a route decision automatically, in every lane, including new images | North star; #809, #810 |
| R2 | Routed images get versioned regions (boxes, then keypoints and masks) with provenance and a config hash | #345 |
| R3 | A consumer adopts regions only when a benchmark of **that consumer's own outcome** shows a gain or no loss | Rollout decision summary |
| R4 | A selection gate measures what its consumers need from a box. A stricter or different standard needs a named consumer that is sensitive to it | This review (F2) |
| R5 | There is one detector path. Retiring the embedded detector must not regress species | #638 |
| R6 | No production step needs a judge, Jev or a label. Calibration happens once and is recorded | North star |
| R7 | Policy belongs to the owner: routes, standards, thresholds and the next step. Agents and Jev may only recommend | Near-dupe v2 R8(c); F5 |

| # | Acceptance criterion | Checks |
|---|---|---|
| AC1 | Scene-label coverage of bird-cohort images is at least _owner_ % (today 20,844 of 28,475 have no label) | R1 |
| AC2 | Direct detector callers either go through the route or record a skip reason (#809) | R1 |
| AC3 | Every live region reader appears in the #857 inventory, classified framing-sensitive, framing-tolerant or unknown | R3, R4 |
| AC4 | Species parity between the selection path and the embedded path is at least _owner_ % top-1 agreement on a fresh sample (#858) | R5 |
| AC5 | New bird-tagged images get a selection with no manual tranche or manifest step | R6 |
| AC6 | Every new preregistration or amendment names the consumer outcome it protects and what stays blocked if it fails (#859) | R4, R7 |

## 3. Findings

The near-dupe v1 drift signals come from [`image-scoring-skills/docs/neardupe-removal-retrospective.md`](https://github.com/synthet/image-scoring-skills/blob/main/docs/neardupe-removal-retrospective.md) and the [near-dupe v2 reset](https://github.com/synthet/image-scoring-skills/blob/main/docs/neardupe-v2/README.md). The **Signal** column names the one each finding repeats.

| # | Finding | Signal |
|---|---|---|
| F1 | The goal narrowed one step at a time | The goal's driver was never re-checked |
| F2 | The gate measured what its consumer doesn't use | No consumer outcome; the standard was assumed |
| F3 | The rubric changed three times | The same gate was retuned a third time |
| F4 | #851 waits on a condition that can't happen | A precondition went stale |
| F5 | Jev picked a policy route | An agent or Jev answered a policy question |
| F6 | A real engineering signal was buried | The measured result went unused |
| F7 | The real automation was starved | A serial blocker that isn't a dependency |
| F8 | Repo and tool hygiene | n/a |

### F1. The goal narrowed one step at a time
The track went through these steps:
1. Reusable regions for every consumer (#345).
2. Retire the embedded detector (#638).
3. Promote 28,475 runs (#694).
4. Calibrate rule R2.
5. Qualify judges: four seats, model chains, receipts (#824, #839).
6. Calibrate the controls: rubric revision 2, then revision 3 with a multi-bird rule (control rounds #837, #838).
7. The owner labels all 390 frames (#841).
8. Measure whether the owner's own standard changed (#851).

Each step is reasonable taken alone. Together they moved six steps away from any production output. The [11-04 plan](localization-rollout-plan-2026-11-04.md#w1-694-promotion-gate) already said that "promoting R2 alone cannot reach detector retirement": 21,032 v0 runs abstain, and 4,146 images have no detection.

### F2. The gate measured what its consumer does not use
- **The rubric grades human framing** (`rubric-r3-20261108.txt`). A box counts as usable only when the head, bill, body, wings, tail, legs and feet are all inside, and the box doesn't take in much background.
- **The only live reader of selections is species.** `BirdSpecies.classify(region=...)` crops with the detector's configured padding (`modules/bird_species.py:347-356` → `modules/bird_detection.py:330-345`, `padding: 0.1` in `config.json`). Subject-aware scoring is off (`scoring.subject.enabled` is absent), and culling stays full-frame.
- **Both paths build `BirdDetector` from one config section.** The localization runner does it at `modules/localization.py:183-210` and the embedded path at `modules/bird_species.py:314-345`: `bird_detect_v1.pt`, imgsz 640, conf 0.25.
- **So an unselected image's species result most likely already comes from the same crop** that promotion would select. Blocking promotion protects nothing for species.
- **Caveats, which [#858](https://github.com/synthet/image-scoring-pipeline/issues/858) measures:**
  - the stored run and the runtime decode can use different renditions;
  - top-box ranking can differ;
  - the 21,032 v0 runs come from another producer.
- **Other readers ([#857 inventory](https://github.com/synthet/image-scoring-pipeline/issues/857#issuecomment-6826325805), 2026-11-12).** No live reader changes its output because of promotion. Readers of unselected images fall back as follows:
  - species to the same detector;
  - keypoints and near-dupe v2 to the current run;
  - overlays to the compat `bird_bbox`.

  The one reader that is sensitive to framing is the near-dupe v2 SAM box prompt, which uses no padding and is study tooling. It reacts to the box *itself*, whether or not it is selected. That points to box refinement (#715), not to re-gating.

### F3. The rubric changed three times
- Revision 2 (11-08), revision 3 (11-09) and the owner-labels route (11-09) each changed the standard after the last result. The owner-labels preregistration says so itself.
- The #469 validation recorded no `poor_crop` in any stratum. The 11-11 result is mostly `poor_crop`.
- So the [report](../reports/localization-owner-validation-694-2026-11-11.md#comparison-with-production) can't compare #694 with #472, and #851 was filed to measure the measuring standard. That is a study of the instrument, not of the product.

### F4. #851 waits on a condition that cannot happen
- [#851](https://github.com/synthet/image-scoring-pipeline/issues/851)'s frozen preregistration draws its sample only after near-dupe archive batch 2 fully finishes (paused at 504 of 2,370).
- On 2026-11-11 the archive selection was withdrawn: batch 1 (646 frames), batch 2 (504) and 108 hard deletes were restored and verified. "Nothing more will be archived under path B" ([`neardupe-archive-design.md`](https://github.com/synthet/image-scoring-skills/blob/main/docs/neardupe-archive-design.md)).
- As frozen, #851 can't start. Amending it is the owner's call (D2).

### F5. Jev picked a policy route
- After the revision 3 panel stopped, the next route was picked by Jev, at the owner's request (0.88): the owner labels all 390 frames, about 3.3 hours.
- Near-dupe v2 dropped a Jev policy answer for the same reason (its D10).
- The choice to keep gating, as opposed to re-checking whether the gate was needed, was never put to the owner as a question.

### F6. A real engineering signal was buried
| Band | Usable | `poor_crop` | `wrong_target` + `no_bird` |
|---|---:|---:|---:|
| large | 121/130 | 5 | 4 |
| medium | 86/129 | 28 | 15 |
| small | 79/126 | 34 | 13 |

- Medium and small fail mostly on boxes that cut off the tail, legs or bill.
- **That is a detector or box-refinement problem.** A SAM 2.1 box-prompted mask can measure and extend a clipped box. The weights are already in `models/` (untracked), and [#715](https://github.com/synthet/image-scoring-pipeline/issues/715) has the measurement half of this.
- **The 390 labels are now development data.** The #694 promotion is closed, so tuning on them re-runs nothing. A fresh held-out set is needed only if some consumer turns out to be framing-sensitive (D6).

### F7. The real automation was starved
Phase A (#694) ran ahead of everything else. Phases B and D don't depend on it, yet they still wait for owner decisions:
- **Phase B:** scene-label backfill for 20,844 images; the v0 decision for 21,032 runs; recovery for the 4,146 images with no detection.
- **Phase D:** route by subject type (#811, #849).

Meanwhile, p1 user-facing bugs wait:
- [#830](https://github.com/synthet/image-scoring-pipeline/issues/830): scoring finishes without `score_general` after Sync;
- [#568](https://github.com/synthet/image-scoring-pipeline/issues/568): EXIF orientation before scoring;
- gallery [#271](https://github.com/synthet/image-scoring-gallery/issues/271): react-virtuoso stack overflow.

### F8. Repo and tool hygiene (for the owner; nothing changed here)
- `gh` returns 401 on both tokens. Issue writes went through the GitHub MCP.
- Not committed in this repo:
  - the `.agent-flow/` init and its `.gitattributes` line;
  - a stale `.agent/workspaces/issue-593/` (2026-10-13);
  - `.claude/settings.local.json.tmp.*`;
  - an untracked `models/sam2.1_hiera_tiny.pt`.
- The agent memory note for #851 still names the archive precondition as pending.

## 4. Healthy, continue as is

- **Scene route** #809 (in progress) and its direct-caller routing (#840). This is R1 work.
- **Sync** fixes (#829, gallery #262, #264) and the capture-key tombstones (#821).
- **Remote GPU runner:** the update runbook (#823). The version fallback, #819, is still open.
- **#780 agreement:** stopped cleanly, missed its bar, and stays a shadow measurement. The eye-mark follow-up moved to `image-scoring-model#48`.
- **Phase F** code items (#681, #682, #319): merged, small, and each one traces to a reader.

## 5. Owner decision register

| # | Question | State | Recommendation (not a decision) |
|---|---|---|---|
| D1 | Which box consumers count right now: species only, or framing-sensitive readers too? | **Open** | Decide after #857. Until then, treat species as the only live consumer |
| D2 | What happens to #694 and #851? | **Open** | Close #694 as failed and recorded (its ACs are met). Cancel #851, or re-scope it without the archive precondition, but only if D1 names a framing-sensitive consumer |
| D3 | The 21,032 v0 runs: relocalize with v1, or a v0-producer policy? | **Open** (plan §6) | Relocalize with v1 after a timed 200-image pilot. That gives one producer, and #858 covers it |
| D4 | What comes next? | **Open** | First #830 and #568 (user-facing, p1). Then Phase B, the scene backfill. Then #857 and #858, which are read-only and cheap. Then Phase D |
| D5 | May Jev or an agent choose a route, standard or threshold? | **Open** | No. They recommend, and the owner decides (R7, as near-dupe v2 R8) |
| D6 | Does box refinement need a framing gate, or only a consumer benchmark? | **Open** | A consumer benchmark only, unless D1 names a framing-sensitive reader. Develop on the 390 #694 labels |

## 6. Follow-up work

| Issue | agent-flow | What |
|---|---|---|
| [#856](https://github.com/synthet/image-scoring-pipeline/issues/856) | af-qio52 | This reassessment |
| [#857](https://github.com/synthet/image-scoring-pipeline/issues/857) | af-p05eq | Inventory of box and selection readers, with framing sensitivity. [Result posted](https://github.com/synthet/image-scoring-pipeline/issues/857#issuecomment-6826325805) |
| [#858](https://github.com/synthet/image-scoring-pipeline/issues/858) | af-w95y8 | Species parity: selection crop vs embedded detector |
| [#859](https://github.com/synthet/image-scoring-pipeline/issues/859) | af-blk0d | Drift guard for preregistrations and amendments |
| [#715](https://github.com/synthet/image-scoring-pipeline/issues/715) | n/a | Comment: extend the mask-tightness signal to box refinement, using the 390 labels as development data |

## Sources and limits

- **Code facts** were checked on `origin/master` at `134437c2` on 2026-11-12.
- **Counts** come from the rollout plan (checked 2026-11-05) and the 11-11 report. They will drift.
- **Transcripts:** only the owner's turns were read, and several exports overlap. Owner quotes come from those turns or from owner-authored docs.
- **Agent memory** for #694 and #851 was used as a pointer and checked against the repo and the issues.
