---
type: Report
title: Geometry-only localization implementation and activation preflight
description: Small-selection species exclusion, transactional box ownership, frozen-cohort refresh operator, and a stopped production preflight for four changed boxes.
resource: reports/localization-geometry-only-activation-2026-10-13.md
tags: [localization, species, rollout, validation]
timestamp: 2026-10-14T00:00:00Z
okf_version: 0.2
---

# Geometry-only localization implementation and activation preflight

The #593 follow-up implements small-selection exclusion and selected-box
ownership, with a tracked bounded refresh command. It is awaiting PR delivery
and deployment. PR #594 already merged the active-selection reader, strict
confidence floor and frozen gate evidence. The small-species precision gate
**remains failed at 0.8123 < 0.85**; the independent rule/4 geometry pass remains
128/128 resolved usable from 130 fresh frames. These are agent-panel labels.

## Acceptance criteria

- **AC-1**: area < 0.005 uses legacy inference without a selected crop; retain
  selection identity/reason, and record `bioclip` species provenance. Exactly
  0.005 remains eligible, including offset boxes; area precedes crop padding.
- **AC-2**: medium/large routing, strict confidence > 0.5, absent/revoked
  selection fallback and lookup-failure fallback retain their behavior.
- **AC-3**: selected projections survive success, missing files, exceptions
  and repairs with region mode on or off. Unselected box writes retain folder
  aggregate invalidation. Guard failures suppress writes and log the failure.
- **AC-4**: PostgreSQL verifies both promotion/write race orders and revocation
  restores the replaced projection without restoring species or embeddings.
- **AC-5**: refresh rejects small/unvalidated/mixed IDs, geometry/identity drift
  and list/artifact hash mismatches before creating a job; admit the frozen
  large/medium cohort with the frozen 369-name list.
- **AC-6**: refresh restores exact non-species keyword source/confidence/relevance
  metadata, including NULL; preserves captions/scores; records each verified
  completion so continuation skips it. Geometry-only promotion preserves small
  species keywords, all embeddings and phase state.
- **AC-7**: (pending) verified deployment, backup/restore proof, all intended
  manifest rows ready or selected by that exact manifest, verified geometry-only
  promotion, seeded 20-image large/medium canary, remaining approved cohort,
  job 6945 paused, and operational receipts before merge/issue resolution.

No new config flags, schema changes or consumer-source adoption are introduced.
Cascade stays shadow, normalized-first reads and crop scoring stay disabled.

## Verification

GPU-shell tests reproduced the routing/ownership regressions before the fix.
The extracted existing refresh procedure failed 14 safety tests before adding
cohort/hash checks. A separate exact-boundary regression failed for an offset
0.005 box before adopting exact decimal area comparison.

Focused routing, species, ownership, refresh, selection, eligibility and judge
panel suites pass **118 tests**. The isolated PostgreSQL suite passes **13 tests** including
both race orders, revocation, small-state preservation and refresh continuation.
The repository CI smoke slice passes **136 tests**. Existing dependency warnings
remain. This is software verification; no new production inference is claimed.

```text
python -m pytest tests/test_refresh_region_species.py tests/test_bird_species.py tests/test_bird_species_regions.py tests/test_bird_species_selection_ownership.py tests/test_localization_selection.py tests/test_judge_panels.py tests/test_bird_species_eligibility.py -q
RUN_POSTGRES_TESTS=1 POSTGRES_HOST=db-e2e POSTGRES_PORT=5432 POSTGRES_DB=image_scoring_test python -m pytest tests/integration/test_localization_selection_e2e.py -m postgres -q
bash scripts/ci/run_fast_smoke_tests.sh
ruff check modules/bird_species.py modules/localization_selection.py scripts/maintenance/refresh_region_species.py tests/test_bird_species.py tests/test_bird_species_regions.py tests/test_bird_species_selection_ownership.py tests/test_refresh_region_species.py tests/integration/test_localization_selection_e2e.py
```

## Production preflight stop

PostgreSQL identity is `image_scoring`, port 5432; job **6945 is paused**.
All **4,401** frozen large/medium identities/geometries match. The 274-row rule/4
manifest has **270 ready** and **four production_changed** rows, none already
selected by that manifest. The four have legacy detector boxes rather than the
expected no-detection sentinel. Their disposition needs review; resetting those
boxes or silently shrinking the manifest would bypass the required preflight.

Frozen artifact hashes and private row receipts remain local under
`.agent/scratch/issue593-activation-20261013/`. Manifest SHA-256:
`8bca5539c4487cd7fa35e1af582de7b829dbe79d3706ce324278e62ebe5d2455`.
No promotion, runtime setting, species/keyword write, new activation backup, service
deployment or normal-service start occurred. The existing dirty research,
release and setup files remain intact; work uses a clean checkout of current
remote master (including #594 and #596).

## Continuation and rollback

1. Review the changed boxes and freeze the authorized manifest disposition.
   Keep the failed species gate unchanged and the evidence frozen.
2. Get the scoped PR checks green. Keep operational completion pending. Hold
   automatic submission/dispatch and verify job 6945, database identity,
   deployed commit, effective config, frozen artifacts and keyword baseline.
3. Deploy clean code with the frozen 369-name list. Preserve the dirty 382-name
   research list separately. Create and restore-test a fresh PostgreSQL backup;
   record its identity and manifest/config/commit receipts.
4. Dry-run the manifest, requiring every intended row ready or selected by that
   exact manifest. Stop on drift. Snapshot small IDs with `--preserve-species`,
   promote geometry, verify selections/projected boxes, and verify preservation.
5. Enable `bird_species.use_regions` and floor 0.5. Snapshot the frozen
   large/medium IDs, refresh a seeded 20-image canary, and verify prediction
   agreement plus complete metadata preservation before the rest. Retain the
   same completion receipt for continuation. Refresh excludes small images.
6. Verify the full cohort, small state and job 6945 before starting normal
   service within existing queued-work authorization. Record receipts before
   merging the PR and resolving #593.

The tracked operator `scripts/maintenance/refresh_region_species.py` provides
`snapshot`, `preflight`, `run`, `restore`, and `verify`. Mutating `run`/`restore`
require `--confirm`; `run` also requires explicit `--ids`, `--species-list`,
`--cohort`, `--full`, `--snap` and `--completed`. Frozen inputs are hash-bound to
the October 9 snapshot and October 10 complete report. Snapshot paths must be
new. `restore` repairs only non-species keyword metadata.

On failure, stop processing and restore the prior region-mode setting. Revoke
only selections owned by this manifest using the existing promotion command.
If species or embedding writes need undoing, recover from the verified
pre-activation backup: selection revocation alone cannot restore those values.
Portrait job 6945 and unrelated research/release work remain separate.
