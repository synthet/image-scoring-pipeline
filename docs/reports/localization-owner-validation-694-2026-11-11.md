---
type: Report
title: Localization owner validation for #694 (2026-11-11)
description: The owner labelled all 390 frames of the frozen #694 sample; no band reaches the 0.90 Wilson bar, so nothing from the unselected-run cohort is promoted.
resource: reports/localization-owner-validation-694-2026-11-11.md
tags: [localization, rollout, promotion, owner-labels]
timestamp: 2026-11-11T00:37:11Z
okf_version: 0.2
---
# Localization owner validation for #694 (2026-11-11)

[#694](https://github.com/synthet/image-scoring-pipeline/issues/694) is the promotion gate for the
current-run cohort: unselected bird-tagged images whose current run, mostly YOLO
`bird_detect_v1`, has a box. After both judge-panel calibrations stopped, the owner labelled the
frozen sample directly. The earlier steps are in the
[promotion-gate continuation](localization-promotion-gate-2026-10-26.md). The
[rollout](../architecture/pipeline/localization-rollout.md) remains the status of record.

## Result

**No band passes, so nothing is promoted.** Under the pre-registration, a failed band ends promotion
for that band. Active selections are unchanged.

| Band | Usable / resolved | Wilson 95% | Unresolved | Passes |
|---|---:|---|---:|---|
| large | 121 / 130 | 0.874 – 0.963 | 0 | no (needs 124) |
| medium | 86 / 129 | 0.582 – 0.742 | 1 | no |
| small (geometry only) | 79 / 126 | 0.540 – 0.706 | 4 | no |

Owner labels per band:

| Band | usable | poor_crop | wrong_target | no_bird | unsure |
|---|---:|---:|---:|---:|---:|
| large | 121 | 5 | 1 | 3 | 0 |
| medium | 86 | 28 | 9 | 6 | 1 |
| small | 79 | 34 | 9 | 4 | 4 |

- **Main failure mode:** `poor_crop` dominates medium and small. Those are boxes that cut off the
  head, bill, tail or legs. Large comes closest, 3 usable frames short of the bar.
- **Sensitivity:** the 3 delegated note conflicts were resolved by judges and Jev under the
  amendment. Counting them as unresolved changes no verdict. The one-per-folder check doesn't rescue
  any band either: large is 43/48, with a lower bound of 0.778.

## Method

- **Frozen inputs, unchanged:** rule R2, the cohort, the exclusions and the 390-frame sample, with
  130 frames per area band.
- **Route:** the owner-labels pre-registration of 2026-11-09 (freeze receipt sha256 `84494706…`),
  plus the note-conflict amendment for frames the owner delegated.
- **Labelling:** 13 blind batches of 30 in a seeded mixed order. Each page showed the whole photo and
  a close view of the box, with no band, confidence, folder or file name. A batch was final once
  recorded.
  - Before a batch was recorded, each label whose note pointed to another outcome was shown back to
    the owner once. Batch 1 had 3 such frames, which the owner delegated. Batch 5 had 1, which the
    owner kept as `unsure`.
  - No counts were shown before all 390 frames were recorded.
- **Bar:** a band passes when the Wilson 95% lower bound of `usable` over resolved frames is at least
  0.90. `unsure` counts as unresolved. The small band was eligible for geometry-only use.
- **Analysis:** `promotion_694_gate.py analyze-owner`, run offline. It writes a create-only result and
  makes no database writes or promotions.

## Comparison with production

The selections live today came through other gates: the #472 re-gate of RTMDet v1 boxes under
`v1_regate_rule/3` (large 93/95, lower bound 0.927; medium 123/123, lower bound 0.970), and rule/4
for small boxes, geometry only. On those numbers the #694 cohort scores far lower. That isn't a
like-for-like comparison:

- **The crop standard is stricter now.** Earlier owner validations almost never used `poor_crop`:
  the #469 validation had none in any stratum. Under the current standard, a cut tail, legs or bill
  makes a box `poor_crop`, and that label explains most of the gap. `no_bird` rates are similar.
- **The populations differ.** The #472 validation sampled only boxes that rule/3 promoted. #694
  samples runs that no rule has selected.

The owner's next goal is to separate these effects. A sample of current production selections will
be labelled blind on the same page and standard. If those also fall well below 0.90, the standard
changed. If they still pass, the YOLO cohort really crops worse. That needs its own pre-registration
and issue. It is observational and changes no selections.

## Provenance

- Owner record sha256: `e4a391a2fe3919fa64d377e518137c731a337776d66d6c6229ae7fbcfeed3c6e`.
- Result: `owner-validation-result-20261111.json`, with manifest sha256 `ad278c67…`.
- The record, every original paste, the note-check files and a per-frame ledger are kept outside git
  and backed up off-machine. The result was also posted on #694.
