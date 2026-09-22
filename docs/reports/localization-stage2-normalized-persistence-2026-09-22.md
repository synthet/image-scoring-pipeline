---
type: Report
title: Localization rollout stage 2 — normalized persistence and compatibility reader
description: Completion report for stage 2; records the schema design, a read-only survey of all 76,089 legacy bird_bbox rows, the verification evidence, and the two things deliberately left undone.
resource: reports/localization-stage2-normalized-persistence-2026-09-22.md
tags: [pipeline, localization, bird_bbox, schema, migration, rollout, report]
timestamp: 2026-09-22T00:00:00Z
okf_version: 0.1
---
# Localization rollout stage 2 — normalized persistence and compatibility reader

**Date:** 2026-09-22 · **Issue:** [#370](https://github.com/synthet/image-scoring-backend/issues/370) · **PR:** [#373](https://github.com/synthet/image-scoring-backend/pull/373) · **Status:** landed and **dormant**; live import not yet run

Stage 2 of [localization-rollout.md](../architecture/pipeline/localization-rollout.md). Everything
is additive and inert: nothing writes the new tables in production, `images.bird_bbox` remains the
sole authority, and `localization.read_normalized_first` defaults to `false`.

## Why two tables

`images.bird_bbox` overloads one unversioned JSONB value with four meanings — never scanned, no
bird, scan failed, one box — carries no detector, source or rendition provenance, and has no room
for a second region, though the detector already retrieves up to `max_det=10` and discards nine.

The design turns on one distinction the old column could not express: **a run row exists for every
attempt, including zero-region ones.** That is what makes `no_detection` a positive, versioned
observation rather than an absence, so an empty `image_regions` set has **no standalone meaning** —
"not attempted" and "attempted, found nothing" are told apart by the run row, never by region count.

A partial unique index on `(image_id, detector_key) WHERE is_current` does double duty: the
compatibility reader's hot lookup, and a structural guarantee that two current attempts per detector
cannot exist. Attempt history is immutable; retry scheduling deliberately lives elsewhere — these
tables store facts, not queue state.

There is **no dual-write** to `bird_bbox`: it participates in live bird-species work selection and
completeness, so writing it would change production behaviour.

## Survey of the live column (read-only)

The population is materially more uniform than the rollout plan assumed:

| Rows | Legacy shape | Normalized |
|---:|---|---|
| 41,001 | box, uniform keys `area_frac,conf,img_h,img_w,x1,x2,y1,y2` | `detected` |
| 35,085 | `{"detected": false}` | `no_detection` |
| 3 | `decode_error: …` | `terminal_error` |
| 320 | `NULL` | not attempted (no row) |

**Zero** constraint violations among the 41,001 boxes — no missing dimensions, no inverted or
out-of-frame coordinates, no out-of-range confidences. And **no `detector_unavailable` sentinels at
all**, so the plan's `retryable_error` import path is implemented but unexercised by this library.

## Three decisions worth recording

1. **An unrecognised payload becomes a *visible* `terminal_error`** with code `malformed_payload`,
   never a silent `no_detection`. A bad row has to stay findable; guessing would erase the fact that
   something went wrong.
2. **Unusable geometry yields a `detected` run with no region**, not a clamped box. The detection is
   a historical fact; clamping would invent a box nobody detected.
3. **Coordinates normalize against the `img_w`/`img_h` in the payload itself**, never the current
   `images` row — the file may have changed since the scan. They land in
   `coord_space = legacy_unverified`, explicitly not the verified display space, because EXIF
   orientation was never recorded.

`error_detail` is path-redacted for logs and support bundles; `legacy_payload` keeps the original
verbatim, which is what makes byte-for-byte reproduction possible at all.

Retryability is **not** restated: `modules.bird_detection.RETRYABLE_BBOX_ERRORS` remains the single
source of truth and `classify_legacy_bbox` defers to it, with a test that fails if the two drift.

## The reader

With the flag off — the default — `read_bird_bbox` is exactly `SELECT bird_bbox FROM images`: same
value, same semantics including `None` for never-scanned. That equivalence is what makes it safe to
land before anything writes the new tables.

With the flag on it projects the current run back to the legacy shape and falls back to the column
when no current run exists. The fallback is not an optimisation: during the import, and for any
image it skipped, the column is still the only source, and a missing run must not read as "no bird".
A sentinel distinguishes "no current run" from a run that legitimately projects to `None` —
returning `None` for both would make a missing run indistinguishable from a never-scanned image and
silently skip the fallback. A normalized lookup that raises falls back rather than propagating: a
reader must never take down a caller that has a working legacy column.

## Verification

All on scratch databases (`loc_stage2_scratch`, `loc_stage2_runtime`); **production was read-only
throughout**.

- Migration upgrade → downgrade → re-upgrade clean; both tables fully dropped on downgrade.
- **Migration and runtime DDL produce identical schemas** — 38 columns, 12 constraints, 8 indexes,
  zero diff. That is the [DB_SCHEMA.md](../technical/DB_SCHEMA.md) dual-source rule checked rather
  than assumed.
- Constraints exercised directly: bad status, orientation 9, zero width, out-of-range / inverted /
  zero-area geometry, confidence > 1, negative rank, duplicate `(run, class, rank)` and a second
  current attempt per detector are **rejected**; a second current attempt for a *different* detector
  and an equal rank in a different class are **accepted**; deleting a run cascades its regions.
- Import over 753 payloads copied from the live column plus 6 deliberately hostile shapes: dry run
  writes nothing → pass 1 writes 709 runs / 400 regions → pass 2 skips all 709, adds 0 regions.
  NULL rows get no run; 709 non-null rows map 1:1.
- **All 709 rows reproduce their original payload byte-for-byte**; the synthesis path round-trips
  pixel-exact.
- All four hot read paths use index scans, no sequential scans.
- Storage ~520 B/run and ~553 B/region → **~59 MiB** extrapolated against a 4,743 MB database.
- Tests: 45 unit (no database) + 9 PostgreSQL E2E.

Regression check on isolated `git archive` exports with an identical command: `master` failed 36,
the branch failed 30, **branch-only set empty**. The 6 master-only failures are export artifacts
(missing untracked fixtures), not real differences.

## Bugs found in passing

- A **server-side named cursor is invalidated by the per-batch commit**. Replaced with keyset
  pagination, which also makes an interrupted import resumable.
- **`POSTGRES_APP_TABLES` is a hand-maintained list** that new tables silently miss. Both tables are
  now registered, and `DB_SCHEMA.md` records that a new table belongs in three places — migration,
  runtime DDL, truncate list — not two.
- `docs/technical/DB_SCHEMA.md` had **no OKF frontmatter at all**; the edit in this branch made it a
  changed concept and `okf-bundle-lint` surfaced the pre-existing gap.

## Deliberately not done

1. **The import has not been run against the production library.**
   `scripts/import_legacy_localization.py` defaults to dry run and requires `--yes`.
2. **The reader is not wired into any production read path.** That wiring changes
   `is_image_bird_species_complete`, which feeds bird-species work selection, and it wants
   database-backed verification.

## Environment notes

- `alembic` is declared in `requirements.txt:38` but is absent from the `image-scoring-gpu-shell`
  image, which builds from `requirements/requirements_wsl_gpu.txt`. Migrations cannot be run there
  without installing it first.
- `tests/conftest.py:13` defaults `POSTGRES_PORT` to `5433` (the compose `e2e` mapping). On a stock
  `docker compose up db` the everyday container listens on `5432`, so `postgres`-marked suites
  silently skip unless the port is overridden.

## Related

- [localization-stage1-control-plane-2026-09-22.md](localization-stage1-control-plane-2026-09-22.md) — the previous stage
- [localization-rollout.md](../architecture/pipeline/localization-rollout.md) — the plan
- [BIRD_BBOX_CROP_STUDY_2026-08-01.md](BIRD_BBOX_CROP_STUDY_2026-08-01.md) — crop evidence and limits
