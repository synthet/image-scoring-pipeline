---
type: Plan
title: Visual domain router and specialist analysis — reconciliation with existing plans
description: Ingest of the "Visual Domain Router and Specialist Image Analysis" design proposal, mapped section by section onto the scene route, detector cascade, subject-aware scoring, named evidence and species specs; lists what is already owned, what conflicts (SR-1 multi-label), and what is new (macro / focal-plane, generic part model, explicit missingness).
resource: docs/planning/visual-domain-router.md
tags: [planning, routing, scene, localization, evidence, macro, keypoints, culling]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.2
status: proposed
---

# Visual domain router and specialist analysis — reconciliation

> **Status:** proposal ingest, docs only (#448). No code. Source (immutable):
> [raw/2026-09-27-visual-domain-router-design.md](../raw/2026-09-27-visual-domain-router-design.md).

The source proposes a cheap, **multi-label** router in front of specialist workflows
(bird, animal, macro arthropod/botanical, landscape, portrait, generic). Each workflow emits
normalized, provenance-stamped **observations** (subjects, parts, regional sharpness, taxonomy).
A separate scoring / meta-model layer turns them into Pick / Keep / Reject. Its central rule:

> Specialist vision models describe the image; the scoring layer decides what those
> observations mean.

Most of this is already planned. This page records where each part lives, so the proposal
doesn't turn into a second, parallel plan. It also lists the three things it adds.

## Terminology

The source's own P0–P9 stage list is **conceptual**, and it says so. Do not introduce "visual
domain router", workflow ids such as `wildlife.bird`, or new `phase_code` values in code. The
canonical names are the ones below.

| Source term | Canonical term / owner |
|---|---|
| Visual Domain Router / workflow router | **Scene route**, [spec 05](../specs/pipeline-streamlining/05-scene-route.md) (#412) |
| Workflow ids (`wildlife.bird`, `macro.arthropod`, …) | Scene labels `wildlife_bird`, `wildlife_mammal`, `wildlife_insect`, `wildlife_herp`, `landscape`, `architecture`, `people`, `other` (spec 05, v1 proposal) |
| Subject detection (P2) | `localization` phase ([rollout Stage 4](../architecture/pipeline/localization-rollout.md)); detector cascade [spec 03](../specs/pipeline-streamlining/03-detector-cascade.md) (#408) |
| Semantic observations / normalized evidence | Named evidence (#423), [subject-aware culling evidence](subject-aware-culling-evidence.md) |

## Section map

| Source section | Already owned by | Fit |
|---|---|---|
| §4, §7 multi-label router | Spec 05 (#412); decision **SR-1** | **Conflict**, see below |
| §6, §17 conditional execution, confidence fallback | Spec 05 AC-7/AC-8: skip detection only at high confidence; the cascade is the safe default; AC-4 caps wildlife false skips at ≤ 2% | Aligned. The source's "medium confidence → cheap confirmation detector" is what the default cascade already does. |
| §9.1, §10 bird / animal subject detection | Rollout Stage 4; cascade YOLO-640 → COCO animal → small-box refine (spec 03) | Aligned |
| §9.3, §10 head / eye anatomy | [Model roles](models/subject-evidence-model-roles.md): bird head/eye keypoints and mammal keypoints; `image-scoring-model` eye-evidence spec | Aligned for eyes and head. Wings, tail and limbs are not specified anywhere. |
| §9.4, §11.3 regional sharpness, subject vs background | Spec 04 (#409) crop IQA; #423 named evidence | Aligned. Background sharpness as its own measure is implicit only. |
| §9.2, §F species / taxonomy, alternatives + confidence | Spec 06 (#413) two-level BioCLIP 2; #422 abstention | Aligned. The source also says "not a blocker for the MVP", which matches spec 06 running after localization. |
| §13 observation separate from judgment | Rollout invariants (shadow, no production writes before a gate); Stage 6 consumer policy; #423 | Aligned |
| §14–15 cluster-relative features, shared cluster hypotheses | #424 burst sub-segmentation; [within-burst plan](within-burst-evidence-plan.md); ranker in subject-aware evidence idea 1; species burst/folder suggestions (#422) | Aligned |
| §16 provenance | Rollout Stage 2 `image_localization_runs` (one provenance-stamped attempt per image); spec 04 AC-14 invalidates crop scores when region geometry or rendition hash changes | Aligned |
| §18 failure isolation, explicit missingness | Attempt states `detected` / `no_detection` / `terminal_error` / `disabled` (spec 02, rollout Stage 4) | Partly. Covers localization, not per-measurement evidence, see below. |
| §19 flexible persistence, no per-part columns | Stage 2 normalized `image_regions`; spec 05 `image_scene_labels` with a `probs` JSONB column | Aligned |
| §23 human labels | [Human culling labels](human-culling-labels.md) (#415) | Aligned. Region- and attribute-level labels are not in #415's protocol. |
| §24–25 evaluation, ablation ladder A–G | Spec 04 AC-21/22 best-vs-reject paired bootstrap; within-burst Arm A as control | Aligned in spirit. The A–G ladder is a useful ordering for the #415 evaluation. |
| §26 staged inference, decode once | #406 single ~2048 px rendition; #416 per-stage timing | Aligned |
| §27 RAW preview identity | #406 orientation-baked rendition; SR-4 / #418 unrotated CLIP vectors | Aligned |

## Conflict: multi-label routing (SR-1)

The [decision register](../specs/pipeline-streamlining/07-blockers-and-decisions.md) records
**SR-1**: "Store all probabilities and route on the top label. Multi-label adds nothing to
routing." The source argues the opposite. A dragonfly is both `wildlife_insect` and macro, and
a bird in flight is both a bird and an action frame. Both should run.

The two positions are closer than they look:

- Spec 05 already stores every label probability (AC-5). Switching from top-label routing to
  "every label above its own threshold" later needs no new storage.
- Routing only decides what to **skip**. Only confident `landscape` / `architecture` / `people`
  skip detection, and everything else gets the cascade. Top-label routing therefore can't
  starve a wildlife frame of detection. It can only fail to *add* a second workflow.

A second workflow matters only once one exists that the cascade doesn't already cover, such as
a macro focal-plane analyzer (next section). **Proposal:** keep SR-1 for M2. Reopen it when a
second specialist workflow is specced, and decide it on the benchmark's per-label calibrated
thresholds (spec 05 already requires them for the `birds` vs `wildlife` mass-absorption problem).

## What the source adds

1. **Macro as a domain.** No spec covers it. Spec 05 has `wildlife_insect` (species only,
   full frame). Spec 03 lists insects, reptiles and amphibians as a non-goal until an
   open-vocabulary detector is benchmarked. Nothing handles **intentional shallow depth of
   field**, where the question is "is the intended focal plane sharp?", and not "is the
   frame sharp?". Botanical and fungi macro aren't in the label set at all.
   Prerequisites: an open-vocabulary detector benchmark (OWL-ViT / Grounding DINO / YOLO-World,
   none run here), plus macro groups in the #415 label set.
2. **A generic subject → part model.** The keypoint roles cover eyes and head (bird, mammal).
   The source generalizes this to typed parts (head, eye, wing, tail, limb, compound eye,
   cephalothorax …), each with a box, mask or keypoints and per-part visibility, sharpness,
   exposure and occlusion. This matches the `image_regions` direction. Before adding part types
   beyond eye and head, define them as region kinds rather than columns.
3. **Explicit per-measurement missingness.** The source asks for `value = null` plus a status
   (for example `unavailable`), never a fabricated 0. Localization already has attempt states.
   The #423 named-evidence contract should state the same rule for each criterion, so that
   "eye not found" is never read as "eye soft". This is small enough to fold into #423 directly.

## Corrections to the source

- §31 fast test command includes `not firebird`. Firebird is decommissioned. Use the subset in
  [CLAUDE.md](../../CLAUDE.md): `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`.
- §32 activates `~/.venvs/tf`. That environment is optional. The primary environment for scripts
  and `scripts/doctor.py` is the `image-scoring-gpu-shell` container.

## Follow-ups

- Missingness rule (item 3): proposed on #423 as an addition to the v0 output contract.
- SR-1 revisit trigger: added to the [decision register](../specs/pipeline-streamlining/07-blockers-and-decisions.md).
- Macro / focal-plane domain (item 1): #449, at `stage:backlog`, blocked on an open-vocabulary
  detector benchmark, macro groups in #415, and the #412 benchmark.
- This ingest: #448.

## Related pages

[Pipeline streamlining](pipeline-streamlining.md) ·
[spec hub](../specs/pipeline-streamlining/INDEX.md) ·
[subject-aware culling evidence](subject-aware-culling-evidence.md) ·
[model roles](models/subject-evidence-model-roles.md) ·
[localization rollout](../architecture/pipeline/localization-rollout.md) ·
[human culling labels](human-culling-labels.md)
