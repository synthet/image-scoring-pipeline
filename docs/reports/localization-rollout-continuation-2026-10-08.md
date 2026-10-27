---
type: Report
title: Localization rollout continuation
description: Merged retry fix loaded, selected-region keypoint coverage completed, and species shadow comparison verified.
resource: reports/localization-rollout-continuation-2026-10-08.md
tags: [localization, rollout, operations, verification]
timestamp: 2026-10-08T22:48:09Z
okf_version: 0.2
---
# Localization rollout continuation

This continuation follows the [October 7 operations report](localization-rollout-operations-2026-10-07.md)
and the [ordered rollout gates](../architecture/pipeline/localization-rollout.md#what-is-left).
The strict retry fix is merged and loaded. Selected-region keypoint coverage is complete.
Stage 4's production automatic-lane gate remains pending genuine eligible work.

## Retry fix and runtime

[PR #577](https://github.com/synthet/image-scoring-pipeline/pull/577) merged at
`474cdea6b8d3608598ea5fb33473a77795ae42f6`; all eight checks succeeded.
The existing WebUI container was stopped at the start of this continuation.
It was started with the mounted source containing the retry patch. Source inspection
confirmed the runner enters `running` before recording a selected image's outcome.
Runtime source version remains 8.18.0; this patch adds no migration.

The isolated PostgreSQL repair regressions passed **3 tests, zero skips**, covering
strict recovery and preservation of cooling-down/exhausted phase rows:

```powershell
docker exec -e POSTGRES_DB=image_scoring_localization_fix_test_20261007_6935 -e RUN_POSTGRES_TESTS=1 -e PYTHONPATH=/app image-scoring-gpu-shell python /app/.agent/scratch/localization-strict-pytest.py tests/integration/test_localization_repair_e2e.py -q -o addopts= --disable-warnings -rs --junitxml=/app/.agent/scratch/localization-resume-repair-final-20261008.xml
```

The health endpoint returned `healthy`; the dispatcher was running, its queue empty
and active runner null. Auto-drive remained disabled. Localization, new-images-only
policy and repair were enabled; `bird_species.use_regions` remained false.
No configuration, detector defaults or enablement timestamps were changed.

## Selected-region keypoints (#492)

A read-only audit of rule `v1_regate_rule/3:a1c2e1f64b24cc79` found current final
keypoint outcomes on 4,397 of 4,401 active selected regions: 4,366 `detected`,
31 `no_keypoints`, and four regions with no keypoint history.

The canonical selection-aware backfill dry run on the four missing image IDs
reported four detections and four visible eyes, with no source or rendition skips.
One apply pass then persisted those four additive shadow outcomes in 11 seconds:

```powershell
docker exec image-scoring-gpu-shell python scripts/backfill_region_keypoints.py --selected-by v1_regate_rule/3:a1c2e1f64b24cc79 --image-ids 73061,73062,154759,167544 --limit 4 --dry-run
docker exec image-scoring-gpu-shell python scripts/backfill_region_keypoints.py --selected-by v1_regate_rule/3:a1c2e1f64b24cc79 --image-ids 73061,73062,154759,167544 --limit 4
```

The post-write audit found **4,370 detected + 31 no_keypoints = 4,401 final outcomes**,
with zero missing selected regions. These results attach to the selected regions,
not the current v1 shadow boxes. No re-localization, keyword, score, phase-status,
selection or image-file writes were performed by the backfill. The existing verified
backup and restored reference from the October 7 report remain available.

## Selected-region species comparison (#493)

The 20-image pilot completed without skips in 29.36 seconds. The canonical
full-cohort comparison then finished in **3,476.12 seconds** (about 58 minutes),
classifying **all 4,401 selected images with zero skips**:

| Outcome | Images |
|---|---:|
| Same stored and new top-1 label | 3,149 |
| Changed top-1 label | 977 |
| Newly labelled | 272 |
| Newly abstaining | 1 |
| Both abstaining | 2 |

Of the 4,126 images labelled both before and after, **23.68% changed top-1**.
For 327 of the changed images, the new top-1 was another already-stored species.
Among 1,524 same-label comparisons with actual BioCLIP confidence on the stored
row, confidence rose on 1,009; the mean delta was +0.0316 and median +0.0036.
Stored `auto` and legacy-repair confidences are placeholders and are excluded
from this confidence comparison. These are agreement and confidence observations,
not a human-labelled accuracy gate.

```powershell
docker exec image-scoring-gpu-shell timeout 7200 python scripts/research/bird_crop/species_selection_shadow.py --selected-by v1_regate_rule/3:a1c2e1f64b24cc79 --limit 4401 --out .agent/scratch/localization-resume-20261008-species-full
docker exec -e PYTHONPATH=/app image-scoring-gpu-shell python /app/.agent/scratch/localization-resume-20261008-audit.py
```

The audit verified unique image IDs, exact equality with the persisted 4,401-image
manifest, matching outcome totals, no skips and complete keypoint coverage.
Manifest SHA256: `85024a8f121100fb55a0cc795f55d1b048249e9fdf2b37873444ad80e6e74446`.
The per-image JSON, generated summary Markdown and final audit remain local
artifacts under `.agent/scratch/localization-resume-20261008-*`.

**Policy snapshot.** This successful run used the **360-species list loaded at
startup and threshold 0.1**, with the selected-region crop path and BioCLIP 2.
The list is loaded once and retained for the entire run. During this continuation,
independent workspace work changed the branch to `feat/422-species-abstention`,
commit `6854efc`, expanding the list to 369 species and introducing a 0.5 default
floor. A later 20-image partition pilot used the expanded list and failed the
exact per-image comparison against the original pilot. Its outputs were excluded;
the full retained report comes solely from the successful canonical serial run.
No partitioned full runs were launched. These results do **not** validate the new
369-species / 0.5 policy; repeat the comparison under that policy before using it
to justify a keyword rewrite or promotion.

The initial 60-minute run was stopped after its measured RAW extraction cost
suggested it could exceed that cap. One unchanged-script restart with a two-hour
cap completed successfully. No species keywords, scores, selections, phase status
or production flags were changed by either comparison. `bird_species.use_regions`
remains off, and the small promotion stratum remains in shadow.

## Production automatic-lane gate

The persisted bird boundary remains `2026-10-04T23:07:14.479257`. Production has
zero images indexed at or after it and zero current retryable bird-localization
runs. Its 79,438 images and 4,401 active selections are unchanged. No production
lane job can be admitted without genuine new or retryable work, so the Stage 4
gate is still pending. A supplied folder of new photos is needed for the next
bounded production observation. Later stage promotions remain behind that gate.
