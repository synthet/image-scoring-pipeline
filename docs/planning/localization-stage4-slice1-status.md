---
type: Report
title: "Localization stage 4, slice 1: work status (#387)"
description: Where the shadow localization phase slice stands when work paused. Covers what is built, the decisions taken during implementation, test evidence, open questions, blockers and next actions.
resource: docs/planning/localization-stage4-slice1-status.md
tags: [planning, localization, bird-detection, pipeline, status]
timestamp: 2026-09-23T00:00:00Z
okf_version: 0.1
---

# Localization stage 4, slice 1: work status (#387)

**State: paused, and not yet ready for review.** The code is complete on branch
`feat/387-localization-shadow` (commit `ef5b5d5`), and the unit tests and new Postgres tests
pass. No PR has been opened yet because the full `-m postgres` suite has not produced a
clean, attributable result (see [Blockers](#blockers)). The board card is at **In Progress**.

Design: [localization rollout § Stage 4](../architecture/pipeline/localization-rollout.md). Epic: #345.

## Summary

`localization` is now a first-class phase. It comes after `metadata` in the phase order,
has `metadata` as its only hard prerequisite, and is *preferred before* `scoring`,
`keywords` and `bird_species`. It runs the existing bird YOLO detector on an explicitly
submitted scope. For each image it writes one provenance-stamped attempt into
`image_localization_runs`, plus up to 10 ranked regions in `image_regions`.

The phase is **off by default** and **shadow-only**:

- `localization.enabled=false`, the default in `config.example.json`, has these effects:
  - The phase is hidden from public phase lists: the scope preview, the folder phase
    summary (through `pipeline_phases.enabled`), and the list of valid tokens in submit
    errors. It is also absent from the OpenAPI descriptions.
  - `/api/runs/submit`, `/api/pipeline/submit` and the job dispatcher reject any
    submission that includes it, with an error naming `localization.enabled`.
  - Auto-drive never targets it.
- The runner writes only to the localization tables, the `localization` phase status and
  job bookkeeping. It makes no writes to `bird_bbox`, scores, tags, species, embeddings or
  consumer phase rows.

| Acceptance criterion | Where | Evidence |
|---|---|---|
| AC-1, AC-2, AC-3 registry | `modules/phases.py` | unit |
| AC-4 gating | `phases.disabled_phase_submission_error`; runs/pipeline submit; `JobDispatcher._start_job`; `LocalizationRunner.start_batch` | unit + parity |
| AC-5 auto-drive exclusion | `runs_autodrive.DEFAULT_TARGET_PHASES` | unit |
| AC-6 to AC-10 outcomes | `modules/localization.py` `localize_image` | unit + Postgres |
| AC-11 phase status | `modules/localization_runner.py` | unit + Postgres |
| AC-12 single current run | `localization.write_run` (one transaction) | Postgres |
| AC-13 provenance / config hash | `detector_config_hash`, `weights_sha256` | unit + Postgres |
| AC-14 skip unchanged | `localization.is_unchanged` | unit + Postgres |
| AC-15 shadow isolation | runner | unit (call allow-list) + Postgres (row counts per table, `images` snapshot) |
| AC-16 job summary | `BatchMetrics`, merged into `jobs.report_json.phases.localization` | unit + Postgres |
| AC-17 public vocabulary | `phases.public_phase_codes`, `seed_pipeline_phases` | unit + parity |
| AC-18, AC-19, AC-20 decode | `localization.decode_for_localization`, migration 0035 | unit + real-NEF smoke |

**Real-file smoke test** (read-only, real detector, gpu-shell):

| File | Route | Pixels | Decode time | Boxes |
|---|---|---|---|---|
| D300 NEF | `raw_jpgfromraw` | 4288×2848 | 0.52 s | 1 |
| Z6ii NEF | `raw_jpgfromraw` | 6048×4024 | 0.74 s | 1 |

## Decisions taken during implementation (please confirm)

1. **Migration 0035 adds `image_localization_runs.decode_route TEXT`.** The issue expected no
   migration, but AC-20 needs somewhere to store the route. `rendition_hash` includes the
   route but cannot be turned back into it, and storing it in `legacy_payload` would misuse
   that column. The column is nullable, and `db_postgres.py` makes the same change.
2. **New route value `DecodeRoute.RAW_JPG_FROM_RAW` (`raw_jpgfromraw`).** It separates the
   full-size `JpgFromRaw` from the reduced `PreviewImage`, which keeps `raw_preview`. Because
   the two decode to different pixels, they also get different rendition hashes.
3. **Localization has its own decoder.** It does not reuse `open_rendition_for_ml`, because
   changing that function would change the pixels production BioCLIP sees. Orientation is
   applied by one rule on every route; for `rawpy` this means passing `user_flip=0` and then
   applying the EXIF orientation.
4. **A `rawpy` failure, including a missing `rawpy` module, is a `terminal_error`**
   (`decode_error`), not a retryable one. AC-9 limits retryable errors to detector problems.
5. **AC-14 reuses only `detected` and `no_detection` runs.** If the current run is a
   `retryable_error` with matching hashes, the image is attempted again.
6. **A `disabled` run's `detector_config_hash` is built from the marker `"disabled"`** in
   place of the weights hash (a detector load failure uses `"unavailable"`). A marker can
   never equal a real digest, so re-enabling the detector always produces a new attempt.
7. **Shadow runs use detector key `bird`, the same key as the stage 2 legacy import.** A
   shadow run therefore takes over "current" from an imported row for the same image. Reads
   are unaffected while `localization.read_normalized_first` is false.
8. **A `pipeline_phases` seed row is kept in sync with the flag.** `seed_pipeline_phases`
   sets the row's `enabled` value from `localization.enabled` at every seed, so turning the
   phase on or off takes effect on the next restart.
9. **`/api/pipeline/submit` gets a `localization` entry branch now**, so enabling the phase
   later needs only a config change.

## Open questions

1. Is migration 0035 acceptable, given that the issue assumed no migration (decision 1)?
2. Should a failed `rawpy` decode caused by the environment (the module is not installed)
   be retryable rather than terminal (decision 4)?
3. Should AC-14's reuse rule also cover `terminal_error`? Today a terminal run has no
   rendition hash, so it is always attempted again.
4. Should the localization job end as `failed` when it contains retryable per-image
   failures? The rollout says the stage "remains failed". This slice completes the job and
   reports the failures in the summary, the same way `bird_species` does.
5. The 2048 px threshold for embedded JPEGs is still the proposed value. Keep it?

## Blockers

1. **The full `-m postgres` suite has no clean result.**
   - The first run hung, idle on CPU, which matches #336 (`test_runs_autodrive.py` hangs when
     Postgres is reachable).
   - A verbose re-run was stopped about 34% through, when work paused. By then it showed
     failures in `test_localization_import_e2e.py` (stage 2) and in
     `test_pipeline_workflow_matrix.py`.
   - The stage 2 import tests **pass when run on their own** on this branch (9/9, as do the
     9 new shadow tests), so those failures depend on which tests ran before them.
   - **Not yet attributed:** the same full-suite run on `master` is needed to tell
     regressions apart from existing flakiness.
2. **The test database is never actually cleaned. This is a pre-existing bug, needs its own
   issue, and is not fixed here.**
   - `db_postgres.truncate_app_tables` re-seeds `pipeline_phases` with
     `enabled = TRUE`, but the column is `SMALLINT`.
   - The resulting error is swallowed by `except: pass`. The transaction is left aborted, so
     the commit silently rolls back the `TRUNCATE`.
   - As a result, `clean_postgres` leaves every row in place, and Postgres tests share
     leftover data. This is the likely cause of the ordering-dependent failures above.
   - Confirmed directly with psycopg2: `column "enabled" is of type smallint but expression
     is of type boolean`.
   - The new shadow tests avoid the problem by limiting their assertions to their own image
     ids and calling `seed_pipeline_phases()` themselves.
3. **#379 (the `POSTGRES_PORT` default)** does not block work in gpu-shell, which sets
   `POSTGRES_PORT=5432`. It still applies to the Windows host.

## Action items

- [ ] Run `-m postgres --deselect` for the #336 hang on both `master` and this branch, and
      compare the lists of failing tests.
- [ ] File an issue for the `truncate_app_tables` boolean-into-smallint rollback
      (Blocker 2). The fix is probably `VALUES (..., 1, ...)` and making the bare `except`
      visible.
- [ ] Answer the open questions, especially 1 (the migration) and 4 (the job status).
- [ ] Open a PR with `Closes #387` and move the card to **Review**.
- [ ] Separate issue: `/task-claim` / `backlog_stage.py` cannot find #387 on the board. The
      item exists, but `gh project item-list --limit 300` does not return it, so the Stage
      had to be set directly by item id.
- [ ] Separate finding, not fixed here: in the production `bird_species` path,
      `open_image_for_ml`'s `rawpy` fallback uses libraw's default rotation, and the result
      then goes through `bake_orientation`. That could rotate a portrait NEF twice. It only
      affects files where embedded-preview extraction fails.
- [ ] Work left in `.agent/scratch/localization-stage4` (an older, broader draft on
      `feat/localization-stage4`, not committed) has been superseded by this branch. It can
      be discarded once this slice is merged.
