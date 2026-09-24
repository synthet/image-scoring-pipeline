---
type: Report
title: Subject-evidence probe — within-burst ranking on the bird-crop label set
description: Arm A (existing whole-frame scores) vs an Arm B probe (six subject-conditioned criteria + composite) on 236 agent-labelled frames in 54 bursts. B matches A overall and leads on best-vs-reject pairs; nothing works on small subjects; the label set is too small to decide.
resource: docs/reports/subject-evidence-probe-2026-09-24.md
tags: [research, culling, evidence, localization, bird-crop, clean-room]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
---

# Subject-evidence probe (2026-09-24)

> **Status:** point-in-time research memo for
> [subject-aware culling evidence](../planning/subject-aware-culling-evidence.md), Stage 6 of the
> [localization rollout](../architecture/pipeline/localization-rollout.md). The database was read
> **read-only**, nothing changed in production, and no code was added to this repo.

## Setup

**Labels:** the 236-frame bird-crop set from the skills repo, `label_set.proposed-522a022f…`:

| Verdict | Frames |
|---|---|
| best | 60 |
| good | 105 |
| reject | 71 |

It covers 54 bursts. The labels are **agent-derived, not human** (multi-agent judges on 25%-padded
bbox crops). Per the [within-burst plan](../planning/within-burst-evidence-plan.md), every number
below inherits that caveat.

**Why not `images.pick_status`:** `pick_status` equals `cull_decision` on every row (31,880 / 24,488 /
20,463). It is the output of `culling.auto_pick_all`, which keeps the top share of each sub-cluster
by `score_general`. Measuring Arm A against it would be circular. No human decisions exist in
`culling_picks` either (3,374 undecided rows, 51 auto-suggested).

**Arm A:** existing non-shadow whole-frame scores:
- `score_general`, `score_technical`, `score_aesthetic`
- LIQE, AVA, SPAQ, TOPIQ, ARNIQA
- `clip_quality_v0`
- KonIQ and PaQ2PiQ, on a subset only

**Arm B probe:** the six subject-conditioned criteria and composite described in the plan (focus,
eye, exposure, composition, noise, context; calibrated composite), computed from the RAW.
- The probe is a **local research instrument**: a behavioural reimplementation of the reference
  design, run on this workstation with locally installed model files.
- It is **not** a candidate implementation and nothing from it enters this repo.
- Its numbers estimate what the *design* can do. Our own implementation must be re-measured.

**Metrics,** within-burst only:
- pairwise concordance over differently-labelled pairs in the same burst (332 pairs; best > good >
  reject; ties count ½)
- best-frame hit rate (the top-scored frame is labelled best)
- 95% bootstrap CIs over bursts

## Results

| Feature | Arm | Pairwise | 95% CI | Best-vs-reject (80 pairs) | Best-hit |
|---|---|---|---|---|---|
| **composite** | B | **0.574** | **[0.517, 0.629]** | **0.669** | 0.326 |
| ava | A | 0.574 | [0.481, 0.661] | 0.525 | 0.324 |
| liqe | A | 0.572 | [0.492, 0.647] | 0.563 | 0.315 |
| composition | B | 0.563 | [0.486, 0.642] | 0.600 | 0.295 |
| eye | B | 0.553 | [0.490, 0.614] | 0.594 | 0.279 |
| score_general | A | 0.548 | [0.461, 0.632] | 0.525 | 0.222 |
| focus (subject) | B | 0.544 | [0.478, 0.604] | 0.625 | 0.217 |
| score_technical | A | 0.527 | [0.434, 0.624] | — | 0.296 |
| noise | B | 0.511 | [0.434, 0.589] | — | 0.291 |
| topiq | A | 0.506 | [0.429, 0.585] | 0.525 | 0.259 |
| clip_quality_v0 | A | 0.500 | [0.420, 0.581] | 0.538 | 0.315 |
| arniqa | A | 0.494 | [0.425, 0.563] | — | 0.333 |
| exposure | B | 0.485 | [0.396, 0.578] | — | 0.310 |
| spaq | A | 0.479 | [0.402, 0.557] | — | 0.157 |

**Paired bootstrap (composite − X), pairwise:**

| X | Difference | 95% CI |
|---|---|---|
| AVA | +0.000 | [−0.091, +0.101] |
| LIQE | +0.002 | [−0.089, +0.093] |
| `score_general` | +0.026 | [−0.067, +0.122] |
| `clip_quality_v0` | +0.074 | [−0.018, +0.167] |

**Subject-size slices,** pairwise (tercile 1 = smallest):

| Tercile | Composite | AVA | Subject focus |
|---|---|---|---|
| 1 | 0.527 | 0.509 | **0.469** |
| 2 | 0.620 | 0.615 | 0.594 |
| 3 | 0.573 | 0.597 | 0.568 |

The probe found no subject on 9/236 frames, which fell back to the no-subject cap.

## Reading

1. **Everything is weak within a burst.** No Arm A score's CI excludes chance. The Arm B composite
   is the only feature whose CI does (lower bound 0.517). This confirms the
   [within-burst plan](../planning/within-burst-evidence-plan.md)'s premise that whole-frame scores
   describe the scene, not the frame.
2. **B ≈ A overall, but B leads on the decision that matters.** On best-vs-reject pairs, the
   composite reaches 0.669, subject focus 0.625 and eye 0.594, against 0.525–0.563 for every Arm A
   score. That is only 80 pairs, so it is indicative, not a gate pass.
3. **Region-conditioned, burst-relative focus is not dead.** The
   [focus-measures memo](BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) found classical measures at chance
   as an *absolute* predictor of AF misses. Here, noise-aware, mask-restricted focus *ranked within
   a burst* separates best from reject at 0.625. The two results are compatible: absolute sharpness
   varies with texture and scene far more than with focus, and relativising within a burst cancels
   most of that.
4. **Small subjects defeat everything,** and subject focus falls *below* chance (0.469). This backs
   the plan's **targeted second pass** (fine rendition for small regions) and argues against
   trusting any focus band when the subject is small. Emit `small_subject` as a limitation instead.
5. **Exposure and context carry nothing** here (both below 0.5). Within a burst, exposure barely
   changes. They may still matter across bursts or for the whole-folder keeper score, but they
   should not drive within-burst ranking.
6. **The label set is the bottleneck.** 54 bursts give CIs of about ±0.05–0.09. Separating B from A
   by the plausible margin (~0.05) needs **~300+ bursts of human labels**.

## Consequences for the plan

- **Promote roadmap item 2** (evidence extractor v0 on imported regions) and the best-vs-reject
  metric to the primary Stage 6 measure. Keep composite, focus, eye and composition, and drop
  exposure and context from *within-burst* ranking weights. They stay as display criteria.
- **Add step 0: a human label set.** About 300 bursts of pick/reject labels from you, collected
  with the gallery's compare view or a minimal labelling page, stratified by subject-size tercile.
  Until that exists, no Stage 6 promotion gate can be passed honestly.
- A cheap human-signal source to explore: frames deleted in a folder but still in the DB (for
  example, `2026-01-19` has 45 more XMP sidecars than NEFs). These are real human rejects if the
  deletion was manual.

## Reproduce

The instrument is local to the research workstation and not part of this repo. It reads the label CSV
and the DB (read-only) and writes per-frame evidence to a JSONL cache. The metric code is roughly
50 lines: pairwise within-burst concordance with a burst-level bootstrap. It should be re-implemented
next to `scripts/research/bird_crop/report.py` when our own extractor exists, reusing that module's
verdict vocabulary.
