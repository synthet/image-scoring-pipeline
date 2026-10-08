---
type: Report
title: Localization rollout deployment and bounded validation
description: Revision 0040 deployment, a 34-image production batch, merged strict-retry regression evidence, and the remaining automatic-lane gate.
resource: reports/localization-rollout-operations-2026-10-07.md
tags: [localization, rollout, operations, verification]
timestamp: 2026-10-08T02:32:36Z
okf_version: 0.2
---
# Localization rollout deployment and bounded validation

Revision 0040 is deployed and the delegated culling lifecycle is verified on a
bounded production batch. The Stage 4 automatic repair-lane exit gate remains
pending because production has no eligible new images or current retryable runs.
This report updates the [rollout status](../architecture/pipeline/localization-rollout.md).

The [October 8 continuation](localization-rollout-continuation-2026-10-08.md)
records the subsequently merged and loaded strict retry fix, completed
selected-region keypoint coverage, and species comparison. The statements
below that the fix was local and undeployed describe the October 7 session.

## Deployment and recovery evidence

[PR #575](https://github.com/synthet/image-scoring-pipeline/pull/575) merged #368
at commit `cb26aba`. Runtime source version is 8.18.0. Production upgraded from
its recorded revision 0033 through 0040; the intermediate additive structures
already existed. Both parent/child linkage indexes, both foreign keys and both
ordering constraints were verified, with all constraints validated.

A pre-migration custom dump was catalog-verified. Before the subsequent live
batch, a fresh custom dump of 1,528,642,711 bytes was catalog- and checksum-verified,
then fully restored into an isolated database. Its 421 catalog entries and
revision 0040 restored successfully. Baseline counts matched production:
79,438 images, 6,752 jobs, 12,658 job phases and 4,401 localization selections.
The restore reference remains available and production was not replaced.

The batch backup is
`backups/postgres/image_scoring_before_small_folder_reprocess_20261007_180318.dump`.
Its SHA256 is
`d994e8acdb8fa3749af3e8d0032d110a555031a2e8d5fa95b3eda2cf765b2757`.
Backups and exact image manifests remain local operator artifacts.

## Production batch

Three existing leaf folders contained 8, 12 and 14 selected images. The 34-image
batch used 15 jobs and completed in about 17 minutes. Each folder ran explicit
localization, a culling/keywords/bird_species parent plan, an explicit keyword
refresh, and a final species pass using refreshed keyword eligibility.

| Images | Localization | Culling parent | Delegated child | Keyword refresh | Final species |
|---:|---:|---:|---:|---:|---:|
| 8 | 6921 | 6922 | 6923 | 6924 | 6930 |
| 12 | 6925 | 6926 | 6927 | 6928 | 6929 |
| 14 | 6931 | 6932 | 6933 | 6934 | 6935 |

All jobs completed. Live observations captured `waiting_child` while delegated
work was running. Every child's `parent_job_id` matched its parent, and all six
delegated keywords/species stage projections exactly matched child state,
`started_at` and `completed_at`. No failed/running selected image-phase statuses
or out-of-scope recorded image actions remained. Production image count stayed
at 79,438.

Per-image verification found:

- **Culling:** 34 done.
- **Keywords:** all 34 actually refreshed and done under the explicit refresh jobs.
- **Localization:** 19 newly processed results, one disabled skip, and 14 unchanged
  results reused. Final statuses were 31 done and three skipped; no failures.
- **Species:** all eight currently `birds`-tagged images classified successfully
  in final job 6930. The other two final passes had no eligible bird-tagged images
  and completed as no-ops. Earlier species results remain stored.

Canonical delegated keywords skip complete existing data, including a selected
status reset whose underlying data remains complete. The supported
`POST /api/pipeline/phase/restart-from` keywords route supplied the explicit
refresh; subsequent folders retained their original statuses until real work
ran. A final explicit-ID species pass followed each keyword refresh.

Aggregate quality scores exactly matched before snapshots. Comparing all 458
selected `image_model_scores` rows against the restored baseline found every
model except `clip_quality_v0` exactly unchanged. Culling refreshes this auxiliary
pick/reject model: 31 rows received new timestamps and ten differed numerically
by at most 2.98e-8 raw or 9.24e-7 normalized. These are floating-point differences
in the culling signal; the batch did not rerun aggregate IQA scoring.

The configured remote GPU timed out. The application's existing embedded
fallback performed inference on the local GPU. Health was healthy, queue size
zero, and active runner null after the batch; auto-drive remained disabled.

## Isolated automatic-lane validation

The existing focused policy and lane tests passed: **34 passed** using
`pytest tests/test_localization_policy.py tests/test_localization_lane.py -q -o addopts=`.
These cover bounded attempts, outage holds, core-work gating and exclusion of
localization from auto-drive's blocking buckets.

A separate database cloned from the verified restore completed a two-fixture
fault-injection exercise through the real dispatcher, localization runner,
database persistence and claim machinery in **425.56 seconds**. The injected
detector outcomes were confined to that process; decoding and wall-clock/database
timing were real. The 60-second and 300-second waits and 60-second lane polling
interval were unchanged. No production timestamps or eligibility were changed.

The exercise verified core-work gating and admitted only the two fixture IDs,
with at most one active localization lane job. All three automatic jobs completed.
The two fixtures retried after 118.63/118.66 seconds and then 301.15/301.14 seconds;
the first interval includes the lane's polling cadence. Each had exactly three
attempts: one recovered to `no_detection`/done and the other remained retryable
but exhausted its allowance. The final backlog was new=0, retryable=1,
cooling_down=0, exhausted=1 and pending=0. No fourth attempt was admitted.

This isolated exercise is control-plane evidence. It does not supply eligible
production work or satisfy the production exit gate.

## Strict retry transition fix

The recovering fixture emitted an illegal `failed` to `done` phase-transition
warning. With `database.strict_phase_transitions=true`, this transition raises
an exception after the successful normalized result is persisted and prevents
the retry job from completing. A PostgreSQL regression reproduced that failure
before the fix and passed afterward.

The local runner fix marks each selected, non-deferred image `running` before
processing. Recovery now follows `failed` to `running` to `done`; existing phase
rules remain enforced. Cooling-down and exhausted images are still deferred
before any phase-status write. The fix subsequently merged in
[PR #577](https://github.com/synthet/image-scoring-pipeline/pull/577)
(merge commit `474cdea6`, fix commit `30644ad0`). Loading that revision into
the production process has not been verified.

The focused unit and PostgreSQL suite passed **103 tests with zero skips**.
After strengthening the deferral assertions, all **three repair integration
tests passed again**, including exact preservation of phase rows during cooling
down and exhaustion. Ruff passed on all four changed Python files, and the four
changed documentation concepts passed targeted OKF lint without warnings.
The suite emitted 52 existing Pydantic deprecation warnings. A detector-only
persistence test now explicitly disables scene routing, avoiding a real
classifier and host configuration in that test; dedicated scene-route coverage
remains separate.

PostgreSQL tests ran in a newly created schema-only database. The local launcher
overrides `modules.test_db_constants.POSTGRES_TEST_DB` in that process, retaining
the repository's real schema and cleanup fixtures. It does not use the shared
test database, the populated staging database or the backup reference.

Final verification commands (the launcher and XML evidence are local artifacts):

```powershell
docker exec -e POSTGRES_DB=image_scoring_localization_fix_test_20261007_6935 -e RUN_POSTGRES_TESTS=1 -e PYTHONPATH=/app image-scoring-gpu-shell python /app/.agent/scratch/localization-strict-pytest.py tests/test_localization_phase.py tests/test_scene_route_localization.py tests/test_localization_policy.py tests/test_localization_lane.py tests/integration/test_localization_repair_e2e.py tests/integration/test_localization_lane_e2e.py tests/integration/test_localization_shadow_e2e.py tests/integration/test_localization_phantom_reconcile_e2e.py tests/integration/test_localization_enablement_e2e.py -q -o addopts= --disable-warnings -rs --junitxml=/app/.agent/scratch/localization-strict-regression.xml
docker exec -e POSTGRES_DB=image_scoring_localization_fix_test_20261007_6935 -e RUN_POSTGRES_TESTS=1 -e PYTHONPATH=/app image-scoring-gpu-shell python /app/.agent/scratch/localization-strict-pytest.py tests/integration/test_localization_repair_e2e.py -q -o addopts= --disable-warnings -rs --junitxml=/app/.agent/scratch/localization-strict-final.xml
docker exec image-scoring-gpu-shell python -m ruff check modules/localization_runner.py tests/test_localization_phase.py tests/integration/test_localization_repair_e2e.py tests/integration/test_localization_shadow_e2e.py
docker exec image-scoring-gpu-shell python scripts/okf_lint.py --profile vexlum --only reports/localization-rollout-operations-2026-10-07.md --only architecture/pipeline/localization-rollout.md --only architecture/pipeline/INDEX.md --only reports/INDEX.md docs
git diff --check
```

## Remaining production gate

After the live batch, read-only production checks found zero images indexed at
or after the persisted bird-enablement boundary and zero current retryable bird
localization runs. The three selected folders also had no unindexed RAW files.
The idle lane therefore has no candidates to admit. Explicit legacy submissions
do not demonstrate automatic admission or retry backoff.

The next production observation is a lane job admitting genuine eligible work
while core work is idle, recording the backlog, and re-attempting any retryable
failures on the 1-minute/5-minute schedule. Global localization enablement,
new-images-only policy, enablement boundary, repair settings and production
auto-drive state were unchanged by this continuation. Later rollout promotions
remain subject to the existing [ordered gates](../architecture/pipeline/localization-rollout.md#what-is-left).

## Cloud continuation after PR #577

On 2026-10-07 (America/Chicago), the merged source passed **103 tests with zero
skips** in the cloud CPU environment: 84 focused unit tests and 19 PostgreSQL
integration tests. These include strict retry recovery, cooling-down/exhausted
deferral, automatic admission, shadow isolation, phantom reconciliation and
enablement-boundary coverage. Ruff passed on the runner and the three regression
test files listed below. The unit run emitted 52 existing Pydantic deprecation
warnings.

The PostgreSQL tests used the repository's isolated `image_scoring_test`
database. Read-only checks of the separate cloud application database found
zero images, no bird-enablement boundary and no localization lane jobs. That
database also has no `alembic_version` table; its setup-created schema is not
evidence of a deployed migration revision. No production connection is attached
to this cloud environment. These checks establish regression coverage for the
merged fix, not production deployment or completion of the Stage 4 exit gate.

Commands ran from the repository root with the cloud's prepared Python environment:

```sh
python -m pytest tests/test_localization_phase.py tests/test_scene_route_localization.py tests/test_localization_policy.py tests/test_localization_lane.py -q -o addopts= --timeout=60
POSTGRES_PORT=5432 RUN_POSTGRES_TESTS=1 python -m pytest tests/integration/test_localization_repair_e2e.py tests/integration/test_localization_lane_e2e.py tests/integration/test_localization_shadow_e2e.py tests/integration/test_localization_phantom_reconcile_e2e.py tests/integration/test_localization_enablement_e2e.py -q -o addopts= --disable-warnings -rs --timeout=60
python -m ruff check modules/localization_runner.py tests/test_localization_phase.py tests/integration/test_localization_repair_e2e.py tests/integration/test_localization_shadow_e2e.py
```

### Read-only preflight for the next production cycle

First confirm the selected-region keypoint coverage and shadow species comparison
for #492/#493, as required by the ordered gates. Then verify that the production
runtime has loaded PR #577, and capture its existing configuration, persisted
boundary, backlog and queue state before watching admission. Do not call
`select_candidates()` as a read-only probe: it calls
`ensure_enablement_boundary()`, which can create the boundary.

The following SQL reads the persisted bird boundary and the lane's new-image
eligibility predicate without initializing anything:

```sql
SELECT detector_key, enabled_at
FROM localization_enablement WHERE detector_key = 'bird';

SELECT COUNT(*) AS eligible_new
FROM images i
JOIN localization_enablement le ON le.detector_key = 'bird'
WHERE i.created_at >= le.enabled_at
  AND EXISTS (
    SELECT 1 FROM image_phase_status ms
    JOIN pipeline_phases pm ON pm.id = ms.phase_id
    WHERE ms.image_id = i.id AND LOWER(TRIM(pm.code)) = 'metadata'
      AND LOWER(TRIM(ms.status)) IN ('done', 'skipped')
  )
  AND NOT EXISTS (
    SELECT 1 FROM image_localization_runs r
    WHERE r.image_id = i.id AND r.detector_key = 'bird' AND r.is_current
  );

SELECT COUNT(*) AS current_retryable
FROM image_localization_runs
WHERE detector_key = 'bird' AND is_current AND status = 'retryable_error';

SELECT id, status, created_at, started_at, completed_at
FROM jobs
WHERE input_path = 'SELECTOR_LOCALIZATION_LANE' AND job_type = 'localization'
ORDER BY id DESC LIMIT 20;
```

A missing boundary needs separate operator review; zero counts cannot establish
eligibility in its absence. The retryable count includes cooling-down, exhausted
and metadata-incomplete images, so it is not a ready-to-admit count. Capture the
live dispatcher's backlog log for that split and any detector-outage hold.

For genuinely eligible production work, retain the automatic lane job IDs,
the idle-core/queue observation at admission, per-image attempt times and the
resulting backlog. Where retryable failures occur, verify the 60/300-second
minimum backoff and three-attempt limit, allowing for lane polling. An explicit
legacy submit, an empty development library or injected test failures cannot
supply this production evidence.
