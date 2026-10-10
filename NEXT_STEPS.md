# Localization rollout — next steps

Paused at the user's request on 2026-10-09 (America/Chicago).
Workspace: D:\Projects\image-scoring-backend.
Resume by reading this file before starting work.

## Current state

- Branch: master; HEAD: 1840726be145c023cd3a401f5e3a636d28448750 (PR #590 merge).
- The localization comparison worker was interrupted and verified absent from the GPU shell.
- Docker Desktop's Linux engine became unavailable again during the final handoff checks. Leave it down while paused; restore the existing services only when the user resumes.
- No completed 369-species full-cohort report or partition checkpoint exists. The latest restart stopped during imports, before inference.
- Do not treat the October 8 full comparison as validation of the later 369-species / 0.5 policy.
- No keywords, scores, localization selections, phase status, rollout flags, or original photos were changed by this comparison.
- After requesting this pause, the user authorized committing and pushing this handoff. The comparison remains paused; the broader dirty files are outside this delivery.

## Completed earlier and delivered

- Strict localization repair/retry fix: PR #577, merge 474cdea6b8d3608598ea5fb33473a77795ae42f6. Three isolated PostgreSQL repair regressions passed with zero skips.
- All 4,401 promoted selected regions have final keypoint outcomes: 4,370 detected, 31 no_keypoints.
- The canonical 360-species / 0.1 shadow comparison classified all 4,401 selected images with zero skips. Outcomes: same 3,149; changed 977; now_labelled 272; now_abstains 1; both_abstain 2. This is agreement evidence, not ground-truth accuracy.
- Six rollout documentation files were committed and pushed as 00547329737ebc687a37f0c6725ab415c009ee0c to origin/feat/422-species-abstention following the user's earlier commit-and-push instruction. Do not assume that branch is still checked out.
- Two live automatic localization jobs, 6939 and 6941, processed twelve staged NEFs. Their dated report satisfies the documented one-live-cycle observation condition. No retryable failure occurred, so production 60/300-second retry timing remains unobserved.
- The normal-indexing capture-date boundary defect was fixed by PR #585 / source a055f50 / merge 5f4e2fe3b4e26fae865dbf8ce44fad9d32c5bc2c. Policy now uses images.registered_at; live schema revision 0041 was verified.
- Another session removed the staged NEFs and corresponding DB rows afterward. The live report remains historical evidence; those rows are not expected to exist now. A later check found zero newly registered eligible images and zero active jobs.
- For the wider portrait-job and release work, read docs/reports/localization-rollout-next-steps-2026-10-09.md. Job 6945 was separately paused; this session did not resume it. Release 9.0.0 remains uncommitted work from another session.

## Work attempted in this continuation

Goal: complete the outstanding selected-cohort species comparison under committed #422 policy, using 369 candidate species and an explicit 0.5 threshold.

The committed list was frozen from 6854efcce1e5a447976738392888ccb927866c6c. The current dirty data/bird_species_list.txt is separate research and must not be consumed or overwritten.

An immutable snapshot captured the exact 4,401 selected IDs, image paths, region geometry, selected run/region identities, current stored species baseline, and classifier/canonical-script hashes. The cohort matched the retained manifest.

Ten stored primary species baselines from the October 8 report are now absent; the other 4,391 were unchanged. The new comparison must use the frozen current baseline. Do not silently compare historical outcome counts as though the baselines were identical.

Preflight encountered two infrastructure problems:
1. D: filled completely; an attempted helper write left that ignored helper empty. The user freed space (about 26 GB), and the helper was restored. The frozen snapshot and prior results remained intact.
2. Docker stopped during cleanup. Existing PostgreSQL, gpu-shell, and WebUI containers were restored for validation; Docker became unavailable again at handoff.

Pilot evidence:
- The first 20-image pilot differed from the historical 369-species pilot on one RAW (image 730); 19 matched exactly. It took about 261 seconds.
- After Docker recovery, the repeat exactly reproduced all 20 historical top-three names and probabilities and took about 63 seconds. The earlier pilot is excluded.
- The exact cause of the first discrepancy is unproven. The RAW decode chain has ten-second ExifTool timeouts and fallback routes. Do not claim the intervening #418 orientation fix explains this discrepancy; it did not change the classifier's direct oriented decode call.
- Therefore do not use the retained 360-species predictions to claim an isolated candidate-list effect. Report the current policy's agreement outcomes independently.

First full-partition attempt:
- Part 0 hit a RAW decode failure for image 5248, then progressed to the 1,200-image marker before it was interrupted. It did not produce a final report; those intermediate results were not retained.
- Targeted read-only diagnostics verified the 32 MB source file is readable, has a valid full-size embedded JPEG, and now decodes through the canonical raw_preview route (8256 x 5504). No source file was modified.
- The helper was extended to record actual decode routes, crop pixel hashes, and per-200-image checkpoints. The subsequent restart was paused during imports and produced no checkpoint.
- Final helper syntax/execution validation remains pending because Docker became unavailable. Verify it before a full run.

## Retained local artifacts

All are under .agent/scratch and contain local/private metadata. Keep them local; publish only aggregate evidence.

Current policy:
- localization-policy-20261009-contract.md — scope, budgets, amendments, failed-preflight history.
- localization-policy-20261009.py — adapter around canonical inference, comparison and summary functions; no production writes.
- localization-policy-20261009-species.txt — frozen committed 369-name list.
- localization-policy-20261009-snapshot.json — immutable cohort/baseline/source hashes.
- localization-policy-20261009-context.json — file size/mtime, cropper hash, padding 0.1, model revision.
- localization-policy-20261009-decoder.json — frozen decoder source hash.
- localization-policy-20261009-pilot.json/.md — excluded first pilot.
- localization-policy-20261009-repeat.json/.md — recovered-runtime pilot.
- localization-policy-20261009-control.json — historical 360/.5 calculation; not a validated causal list control.
- localization-policy-20261009-decode-diagnostic.py/.json — image 5248 diagnostic.

Earlier evidence:
- localization-resume-20261008-manifest.json — exact 4,401 IDs; manifest SHA-256 85024a8f121100fb55a0cc795f55d1b048249e9fdf2b37873444ad80e6e74446.
- localization-resume-20261008-species-full.json/.md — completed 360/.1 comparison.
- localization-resume-20261008-species-partition-pilot.json — historical 369-name pilot.
- localization-resume-20261008-final-audit.json.
- localization-resume-repair-final-20261008.xml — three strict repair tests, zero skips.

Frozen candidate-list JSON SHA-256:
dc6984a9fa305db099f7a155d1e319fdf495c0917897c2738d2c5eee79674070.

Model: imageomics/bioclip-2, cached revision
2957b322090f9cb17ae72c71981c7218a28d81e0.

## Resume sequence

1. Check git status and the current branch. Preserve all unrelated changes. Read AGENTS.md and applicable canonical project skills. Use the connected Jev server for unresolved method/permission/sensitivity choices; do not send private photo paths or secrets to it.
2. Check free space and Docker. If the user resumes this comparison, restore the existing PostgreSQL and GPU shell. Inspect the state of the WebUI before restoring it; do not resume portrait job 6945 or submit production jobs as part of this shadow comparison.
3. Validate the saved helper without importing the application:

   docker exec image-scoring-gpu-shell python -c "import ast; from pathlib import Path; ast.parse(Path('/app/.agent/scratch/localization-policy-20261009.py').read_text()); print('helper syntax valid')"

4. Inspect the helper and any artifacts created after this handoff. Verify the frozen species, classifier, canonical script, decoder, cropper/padding, source file metadata, region identities and stored baseline still match. If they changed, retain the old snapshot and establish a clearly dated new baseline; do not overwrite the frozen snapshot or relax assertions blindly.
5. Run the two halves sequentially, one GPU model process at a time:

   docker exec -e PYTHONPATH=/app -e HF_HUB_OFFLINE=1 image-scoring-gpu-shell timeout 5400 python /app/.agent/scratch/localization-policy-20261009.py part --part 0

   Only after part 0 completes successfully:

   docker exec -e PYTHONPATH=/app -e HF_HUB_OFFLINE=1 image-scoring-gpu-shell timeout 5400 python /app/.agent/scratch/localization-policy-20261009.py part --part 1

   Part sizes are 2,201 and 2,200. Each has a 90-minute bound. Measured GPU memory ruled out two simultaneous workers while WebUI models were resident. Do not add parallel workers or change the production model load to accommodate them.

6. Monitor progress, GPU headroom, decode errors, and source stability. If a decode failure or resource problem occurs, retain checkpoints and diagnose it before declaring success. Checkpoints preserve partial results; the helper does not yet automatically resume from them. Do not claim zero skips unless all 4,401 IDs have successful final inference exactly once.
7. When both parts pass, merge and verify:

   docker exec -e PYTHONPATH=/app image-scoring-gpu-shell python /app/.agent/scratch/localization-policy-20261009.py merge

   Required: exactly 4,401 distinct expected IDs, zero final skips, frozen inputs and baseline unchanged, retained decode/crop provenance. The merge refuses changed input/baseline state. Recheck model revision and partition metadata, not only the process exit code.
8. Write a dated aggregate policy-validation report, update docs/architecture/pipeline/localization-rollout.md, report index and log using the docs-wiki workflow, and run targeted OKF lint plus git diff --check. Clarify that the new-image boundary fix is merged/deployed while production retry timing is still unobserved.
9. Keep this as shadow agreement evidence. Do not rewrite species keywords, change rollout flags, enable region reads, alter detector settings, promote crop scoring, or fabricate a live retry event. Broader labelled accuracy, Stage 5 promotion and Stage 6 gates remain separate work.
10. Commit/push only when requested for the new continuation. The earlier requested delivery is already recorded above.

## Concurrent work to preserve

At pause, unrelated modified/untracked files included:
.claude/HOOKS.md, .claude/settings.json, .gitignore, CHANGELOG.md, modules/version.py,
data/bird_species_list.txt, data/bird_species_austin_frequency_proxy_2026-10-09.csv,
data/other_animal_species_list.txt, docs/technical/BIRD_SPECIES_WALKTHROUGH.md,
scripts/research/clip_species_study.py, tests/test_clip_species_study.py,
reports/model-selection-2026-10-01/, and the broader localization next-steps report/index/log edits.

Do not stage these indiscriminately. Never modify .git/config. Preserve .agent/scratch/418/ backups and the staged-data cleanup history recorded in the broader next-steps report.
