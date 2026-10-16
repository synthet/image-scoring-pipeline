---
type: Report
title: Stage 5 region-species activation and rule/4 geometry promotion
description: Production activation receipt for #592/#593 — 4,401 large/medium images refreshed with region BioCLIP, 274 small selections promoted geometry-only, cascade enablement held.
resource: reports/localization-stage5-activation-2026-10-15.md
tags: [localization, species, rollout, validation]
timestamp: 2026-10-15T23:58:00Z
okf_version: 0.2
---

# Stage 5 region-species activation and rule/4 geometry promotion

On 2026-10-15 the staged activation planned in
[the geometry-only report](localization-geometry-only-activation-2026-10-13.md) completed in production:

- **Stage 5 is live.** `bird_species.use_regions: true` and the 0.5 floor are set in live `config.json`.
- **All 4,401 frozen large/medium selections** carry a verified region-BioCLIP species outcome.
- **The 274 rule/4 small selections are active for geometry only.** Species for those images keeps the legacy path, per #598, because the small-species gate failed.

The gates behind these steps are **agent-panel gates, not owner labels**. See
[the gate report](localization-agent-panel-gates-2026-10-12.md).

## Result

| Check | Result |
|---|---|
| Refreshed images, each with a per-image completion receipt | **4,401 / 4,401** |
| `species:*` rows with source `bioclip_region` on the cohort | **3,948**, equal to the frozen same 2,961 + changed 753 + newly labelled 234 |
| Abstentions | 453, equal to the frozen now-abstains 403 + both-abstain 50 |
| Non-species keyword membership and source/confidence/relevance | preserved for every image against the pre-run snapshot |
| Captions, scores, other image metadata | preserved |
| Active selections | rule/3: 4,401; rule/4: 274, including four reviewed replacements |
| Small-image species, phase and embedding state | preserved against the small preservation snapshot |
| Portrait job 6945 | still paused; WebUI not started; no other queued work |

The final check (`verify-final`) re-verified every refreshed image against its frozen prediction and the preservation snapshot.

## Execution

The run used a clean activation image, built from the merged source with no
workspace source mounted. The operator is
`scripts/maintenance/refresh_region_species.py`. It accepts only the hash-bound
frozen cohort and the 369-name list, and runs in batches of at most 200 images.

1. **Pre-activation:**
   - Took a verified backup: `backups/issue593-activation-20261014/image_scoring_pre_activation.dump` (custom format, 1.54 GB, restore-tested in an isolated DB).
   - Added the 546 missing `birds` tags under an explicit approval.
   - The 20-image canary passed (job 6947).
2. **Jobs 6949–6952:** refreshed 833 images.
3. **First stop, image 1037:** the refresh removed `birds:species-exhausted`. Fixed by #599, which reinserts removed non-species rows with their original `created_at`.
4. **Job 6953 stopped on image 14547.** The image's only bird marker was `birds:species-exhausted`. When the refresh wrote its species (American Wigeon 0.5679, identical to the frozen prediction), it also added a parent `birds` tag. The preservation gate correctly rejected the new tag. Per the failure policy, region mode was restored off and the manifest selections were revoked.
5. **Fix #608 (merge `6366c50`):** restore also deletes non-species rows that are absent from the snapshot, so membership matches the snapshot in both directions. A real-Postgres regression test fails without the fix and passes with it.
6. **Rebuilt the clean image at `6366c50`:** 48 focused tests pass, the 369-name list matches its frozen hash, CUDA works. Its source differs from the previous image only in #608's files.
7. **Restored 14547 to its snapshot,** removing the `birds` row and then the unverified species row left by job 6953. After that, all 3,522 pending images matched the snapshot exactly, and the 879 completed images re-verified.
8. **Re-promoted the 274 rule/4 selections and enabled region mode.**
9. **Jobs 6986–7003** refreshed the remaining 3,522 images in 18 batches (23:04–23:58 UTC) with no failure. The final verification passed.

Receipts, snapshots and logs stay in the ignored
`.agent/scratch/issue593-activation-20261014-approved-tags/`. Stopped attempts are archived under `attempt1/` to `attempt3/`.

## Rollback

- **Stage 5:** remove `bird_species.use_regions` and `bird_species.min_confidence` from `config.json`. The activation operator's `disable` action restores the recorded previous values.
- **Rule/4 geometry:** run `promote_localization_selections.py revoke` on the rule/4 manifest. Each selection's captured previous box is restored.
- **Species and embedding recovery:** needs the pre-activation backup. Revocation alone does not restore them.

## Not done

- **#408 cascade enablement is held.** AC-17/AC-18 pass, and AC-15 holds: there are zero `coco` and zero `subject_cascade` runs. But `onnxruntime` is missing from the production image and from the requirements files. With `localization.cascade.enabled: true`, the RTMDet fallback would report `provider_unavailable`. That isn't the gated configuration, so the shadow runs would be misleading. Add the dependency to the image first, then enable the flag and observe.
- **Small-crop species remains failed** (Wilson lower bound 0.8123 < 0.85). It needs a new pre-registered evaluation.
- **Other #422 items stay open:** range list, burst propagation and folder shortlist.
