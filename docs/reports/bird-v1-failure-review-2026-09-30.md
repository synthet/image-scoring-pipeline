---
type: Report
title: Bird v1 shadow-rescan failure review
description: Complete owner diagnosis of 79 false detections and 35 bad primary crops from the stratified v1 development sample, with diagnostic alternative boxes.
resource: reports/bird-v1-failure-review-2026-09-30.md
tags: [report, localization, bird-detection, shadow, owner-labels, failure-review]
timestamp: 2026-09-30T00:00:00Z
okf_version: 0.2
---

# Bird v1 shadow-rescan failure review (2026-09-30)

## Scope and provenance

This is the completed second-pass review of the 114 detected failures in the
[v1 owner sample](bird-v1-owner-review-2026-09-29.md): 79 frames blindly labelled
**no bird visible**, plus 35 bird-visible frames whose v1 primary box was graded
**poor crop** or **wrong target**. The owner used the private
`failure_review/index.html` page to classify false-detection causes and grade
every available alternative box. The final CSV has 236 rows because a case with
multiple alternatives exports one row per graded candidate. All 114 cases are
marked reviewed, and the CSV matches the frozen case and candidate manifest.

The review JPEGs, final CSV, and manifest remain gitignored under
`.agent/scratch/bird_v1_owner_labels/failure_review/`. The tracked
[`analyze_v1_failure_review.py`](../../scripts/research/detector_benchmark/analyze_v1_failure_review.py)
validates and replays the counts without a database. SHA-256 of the private
inputs used here:

| Input | SHA-256 |
|---|---|
| `manifest.json` | `277a029e68ba4659323016a4c1754e84afc66f3f93ebfcf8be329e2a7b114d49` |
| final owner CSV (`partial_results_2.csv` in private scratch) | `68d837e72cb7b7b6c6702bed16f7514204d942d91785774407300188e5ca46aa` |

The RTMDet and YOLO-refined candidates were inferred from the **review JPEGs**,
not the production inference renditions. These labels diagnose failure modes
and suggest candidates; they do not validate a deployed cascade or a promotion
rule.

## Owner labels

| Failure group | Owner result | Cases |
|---|---|---:|
| No-bird v1 detections | Other animal | 39 |
| | Scene or texture | 22 |
| | Other object or person | 18 |
| **No-bird total** | No label corrections or unsure causes | **79** |
| Bad v1 primary | At least one usable alternative | 26 |
| | No usable alternative | 9 |
| **Bad-primary total** | All alternatives graded | **35** |

Of the 27 **poor-crop** primaries, 19 had a usable alternative. Of the eight
**wrong-target** primaries, seven had one. Five of the 35 bad-primary cases had
no alternative box to grade. The remaining four cases without a usable
alternative had candidates, but none were owner-approved.

| Candidate provider | Bad-primary cases with ≥1 usable box |
|---|---:|
| RTMDet animal | 26 |
| YOLO refined RTMDet | 20 |
| v1 secondary | 5 |

These provider counts overlap. Every one of the 26 cases with a usable
alternative had a usable RTMDet box on the review JPEG. Refinement sometimes
offered another usable crop but did not add a newly rescued case in this set.

## False-detection corroboration check

The page originally called any RTMDet animal box at confidence ≥0.25
“agreement.” That was a frame-level co-detection, without a box-overlap test.
The page now labels it as a candidate **anywhere in the frame**. A separate
read-only replay compares each RTMDet animal box with the v1 primary:

| RTMDet condition on 79 known no-bird frames | Cases |
|---|---:|
| Confidence ≥0.25, anywhere in frame | 37 |
| Confidence ≥0.25 and IoU with v1 primary ≥0.50 | 25 |
| Confidence ≥0.40, anywhere in frame | 20 |
| Confidence ≥0.40 and IoU with v1 primary ≥0.50 | 14 |

Thus even a spatial match at these exploratory thresholds can occur on a known
false detection. These checks are descriptive and use review-JPEG candidates;
they are not a calibrated agreement-filter false-positive rate.

## CLI visual second opinions

Two read-only CLI agents reviewed deterministic sheets showing each photo,
candidate boxes, and box crops. They saw the **case kind** and candidate IDs,
but not the owner's cause or alternative-box grades. Thus their presence check
was not blind to case selection. These are disagreement-finding second opinions,
not ground truth or a validation sample. The private outputs and a
`failure_review/panel.html` disagreement queue stay under the same gitignored
scratch directory.

| Comparison with owner | Codex | Antigravity |
|---|---:|---:|
| Cases visually reviewed | 114/114 | 113/114 |
| Exact false-detection cause match | 63/79 | 65/79 |
| Exact alternative-box grade match | 77/152 | 77/139 |

Antigravity's headless read-only permission gate prevented it from inspecting
one dense multi-bird case (image 19140), including a retry split by box sheet.
Codex covered that case. Image 21350 was recovered in three smaller sheets
with minor wingtip/foot overhang explicitly allowed. On the **139 alternative
grades seen by both agents**,
they agreed with each other on 95; Codex matched the owner on 66 and
Antigravity on 77. Exact crop-grade agreement is limited by target choice and
rubric tolerance, especially in multi-bird frames. Do not use these fractions
as model accuracy estimates.

Both agents called **no bird visible** on 78 of the 79 owner-labelled no-bird
frames. On image 40176, Codex suggested a tiny bird outside the v1 box;
Antigravity and the owner labelled no bird. Keep this as a presence recheck,
not an automatic label correction. The agents agreed with each other on
70/79 false-detection causes; their shared cause disagreements with the owner
mostly move examples among animal, texture, and object categories without
changing the no-bird decision.

On 28 alternative-box rows across 16 images, both agents crossed the owner's
**usable versus non-usable** boundary in the same direction. In 25 rows the
owner marked usable and both agents marked poor crop; two owner wrong-target
rows and one owner unsure row were marked usable by both agents. These should
be adjudicated with a fixed target-bird and crop-tolerance rubric before the
labels are reused for an automated primary-choice rule. The private panel
page links directly to the corresponding box sheets. Owner labels remain the
source of truth for the results above.

## Rollout decision

**Keep all 16,666 v1 detected runs in shadow.** This review diagnoses the
original primary failures and identifies possible replacement crops, but the
sample was deliberately stratified and folder-balanced. Its fractions are not
estimates for the 35,209-image legacy-miss cohort or the full library. The
candidate provider and threshold choices were inspected on this development
set; none can validate itself.

Next, reproduce promising RTMDet candidates on the production inference
rendition, define a deterministic primary-selection and false-positive rule,
then measure it on a newly frozen, independent owner-labelled sample. That
sample must assess **bird presence and crop usability together** in each
proposed promotion stratum. Only then consider a guarded subset promotion to
`images.bird_bbox` and downstream eye-keypoint refresh. This review made no
production database changes.

Replay the final CSV locally:

```powershell
python scripts/research/detector_benchmark/analyze_v1_failure_review.py `
  .agent/scratch/bird_v1_owner_labels/failure_review/manifest.json `
  .agent/scratch/bird_v1_owner_labels/failure_review/partial_results_2.csv
```
