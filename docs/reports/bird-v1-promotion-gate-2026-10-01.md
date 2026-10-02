---
type: Report
title: Bird v1 shadow-box promotion gate
description: Production-rendition reproduction of the failure-review rescues, the frozen RTMDet promotion rule fitted on development labels, and its independent owner validation, which no stratum passed.
resource: reports/bird-v1-promotion-gate-2026-10-01.md
tags: [report, localization, bird-detection, shadow, promotion-gate]
timestamp: 2026-10-01T00:00:00Z
okf_version: 0.1
---

# Bird v1 shadow-box promotion gate (2026-10-01)

The [failure review](bird-v1-failure-review-2026-09-30.md) set three conditions for promoting
any of the 16,666 v1 shadow detections to `images.bird_bbox`. This report covers the first two
then runs the third, an independent owner validation (#469). **Result: no stratum passed, so all 16,666 boxes stay in shadow.** The harness is
[`v1_promotion_gate.py`](../../scripts/research/detector_benchmark/v1_promotion_gate.py). It only
reads the database. Its snapshot, probe output, rule and sample stay in gitignored
`.agent/scratch/bird_v1_promotion/`. **No production rows changed.**

## Gate 1 — reproduction on production renditions: passed

RTMDet and the small-box YOLO refine were rerun on the production inference rendition
(`decode_for_localization`) of all 16,666 snapshotted images. Every decoded rendition hash
matched the stored v1 run, so the boxes come from the same pixels v1 saw. There were no
decode errors.

On the 114 failure-review cases:

| Check | Result |
|---|---:|
| Bad-primary cases with an owner-usable alternative on review JPEGs | 26 |
| … with a matching production box (IoU ≥ 0.5) | **26** |
| Usable RTMDet candidates reproduced | 37/37 |
| Usable refined candidates reproduced | 30/34 |

Restricting corroboration to RTMDet's COCO **bird** class roughly halves the false-detection
support. At conf ≥ 0.40 with IoU ≥ 0.5 to the v1 primary, 7/79 known false detections are still
corroborated, versus 14/79 for any animal class. Even so, corroboration by itself is not a
precision guarantee.

## Gate 2 — rule fitted on development labels: frozen, not validated

Fifteen settings were evaluated on the 144 detected development frames. Each was scored against the
owner presence labels plus every graded primary and alternative box, matched by IoU ≥ 0.5.
On **unweighted** dev precision, no setting reached the 0.90 floor; the best was 0.83 (19/23).

The development sample drew 16 frames per confidence × area cell, while 73% of the population
is high-confidence. With the owner's approval, the criterion was therefore switched to
**population-weighted** dev precision. This switch came after the unweighted result was known, and
`rule.json` records that. Under the weighted criterion, the setting with the most estimated usable
promotions was chosen:

| Frozen rule `ecbb646e6649b3c2` | |
|---|---|
| Promote when | an RTMDet `bird` box has conf ≥ 0.55 (v1 overlap not required) |
| Promoted geometry | the RTMDet box, replaced by its YOLO refine when that overlaps (IoU ≥ 0.3) |
| Dev result | 27 promoted, 22 usable, 3 no-bird, 2 ungraded; weighted precision 0.942 |
| Whole cohort | 7,317 of 16,666 would be promoted; 9,349 stay in shadow |

In every setting, the RTMDet geometry beat the v1 primary geometry by 15–25 points of dev
precision. These are development figures and cannot validate the rule.

## Gate 3 — independent validation: failed

The sample (seed `bird-v1-validation-1`) excludes all 216 development images **and every
development folder**. Strata use the rule decision × promoted-box area, with at most one image
per folder per stratum.

| Stratum | Population | Sample |
|---|---:|---:|
| promote_large | 736 | 60 |
| promote_medium | 1,680 | 60 |
| promote_small | 291 | 27 |
| keep_shadow | 4,113 | 60 |

Two limits should be stated before labelling:

- **Folder exclusion is broad.** It removes 9,702 of the 16,666 images, so the validation
  population covers 6,820 images from unseen folders. A passing result shows the rule generalises to
  new folders. Applying it to the development folders afterwards rests on that.
- **promote_small cannot pass.** Its 291 images sit in only 27 folders, and even 27/27 usable gives a
  Wilson lower bound of 0.875. Under the per-folder cap, this stratum stays in shadow whatever the
  labels say.

The owner labels each image with a private, blind, two-step page
(`validation/page/index.html`). Presence comes first, on the bare photo. Then the proposed box
appears for a usable / poor / wrong grade. The page shows no stratum, decision, provider or
confidence. **Pass condition:** a stratum may be promoted only if its present-and-usable Wilson 95%
lower bound is ≥ 0.90. The `analyze` action computes this from the exported CSV.

| Frozen input | SHA-256 |
|---|---|
| `snapshot.json` | `c7df702e54c58c6894b07b461aa5a18d10b0c24d399f1dbcd2555b63ab2a5a05` |
| `probe_production.jsonl` | `3e6b64f96e086691bd7ceb5e982a1f1fd28dcfc3dca389366c828937c0d9857a` |
| `rule.json` | `1c1d8a03a4e61acd65c274f13d59de2fda7d3a83b62bc9de569531c56fcc6bb5` |
| `validation/cohort.csv` | `8901fcd1769ea7e4f3f351d8904fe998e1bfabbb8c4999dc95216314a5751330` |
| `validation/sampling.json` | `1fa3841d8b2e5c0d47e0e19b19976de059e5fda3518309d6c6a537fe33ecb0a6` |

### Owner validation result

The owner labelled all 207 images (`labels.csv` SHA-256
`e63373cf1345a9c83b9af7410bc2353219f6952048bdd43d1971a16a8eb45d11`). "Unsure" counts as not usable.

| Stratum | Present and usable | Rate | Wilson 95% | No bird | Wrong target | Poor crop | Unsure | Passes |
|---|---:|---:|---|---:|---:|---:|---:|---|
| promote_large | 50/60 | 0.833 | 0.720–0.907 | 6 | 2 | 0 | 2 | no |
| promote_medium | 53/60 | 0.883 | 0.778–0.942 | 4 | 1 | 0 | 2 | no |
| promote_small | 19/27 | 0.704 | 0.515–0.842 | 2 | 2 | 0 | 4 | no |
| keep_shadow | 23/60 | 0.383 | 0.271–0.510 | 31 | 3 | 3 | 0 | — |

The population-weighted rate across the promote strata is 0.850, below the 0.94 the development
fit suggested.

**Decision: nothing is promoted.** The rule clearly separates the two sides: 85% of promoted
boxes are usable, against 38% of the boxes it keeps in shadow. The residual errors are still mostly
**no-bird** frames, though: 12 of the 147 promoted sample images had no visible bird. Even
counting "unsure" as usable, the best stratum (medium, 55/60) would have a lower bound of about
0.84. No stratum is near the 0.90 bar.

The rule also leaves many good boxes behind. About 38% of the 4,113 keep_shadow images
outside the development folders had a usable v1 primary.

Possible next steps, each needing a new frozen rule and a new validation sample. This sample has
now been seen, so it cannot validate a rule tuned on it:

- add a second false-positive signal for the no-bird frames, for example BioCLIP or a scene
  classifier, rather than raising the RTMDet threshold;
- accept a lower, explicitly agreed precision bar for a consumer that tolerates errors, such
  as shadow-only crop scoring. Production `bird_bbox` feeds species work selection, so the 0.90 bar
  stays for it;
- improve the detector itself, for example by retraining with the 79 + 12 labelled no-bird frames
  as hard negatives.

A read-only check after the runs found all 16,666 current v1 `detected` runs still on the
production no-bird sentinel.
