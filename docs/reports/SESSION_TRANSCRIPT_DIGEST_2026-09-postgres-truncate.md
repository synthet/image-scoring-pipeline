---
type: Report
title: Session digest — Postgres test truncate rollback (#399)
description: Public summary of why truncate_app_tables() left image_scoring_test dirty and how the fix was validated — distilled from issue #399 and debugging sessions, without operator transcript paths.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-09-postgres-truncate.md
tags: [session, digest, postgres, testing, truncate]
timestamp: 2026-09-27T16:55:00Z
okf_version: 0.2
---

# Session digest — Postgres test truncate rollback ([#399](https://github.com/synthet/image-scoring-pipeline/issues/399))

## Symptom

`truncate_app_tables()` appeared to run, but `-m postgres` tests still saw **leftover rows** (for example
tens of `images` rows with monotonic ids that should have restarted under `RESTART IDENTITY`). The
`clean_postgres` fixture behaved like a no-op.

## Root cause

After `TRUNCATE`, the same transaction re-seeded `pipeline_phases` using Python **booleans** for
`SMALLINT` columns (`enabled`, `optional`, `default_skip`). PostgreSQL rejected the insert; the error
was swallowed (`try` / `except` / pass), leaving the transaction **aborted**. On connection teardown,
`commit()` rolled back — **including the truncate**.

## Fix (landed PR [#427](https://github.com/synthet/image-scoring-pipeline/pull/427))

- Bind **integer** values (`1`, `1 if optional else 0`) or reuse the canonical seed path.
- Ensure reseed failures **cannot silently undo** the truncate (visible log or separate transaction).

## Acceptance checks

| ID | Criterion |
|----|-----------|
| AC-1 | After `truncate_app_tables()`, every table in `POSTGRES_APP_TABLES` is empty and `pipeline_phases` is re-seeded |
| AC-2 | Reseed failure cannot roll back truncate without a visible error |
| AC-3 | Full `-m postgres` suite re-run to surface ordering flakes (see also [#336](https://github.com/synthet/image-scoring-pipeline/issues/336) hang) |

## Related

- [localization-stage4-slice1-status.md](../planning/localization-stage4-slice1-status.md) — cited truncate bug as Postgres E2E blocker
- [TESTING.md](../TESTING.md) — postgres marker and isolation expectations
