---
type: Implementation Plan
title: Database refactor next steps
description: Current schema, keyword-preservation and storage dependencies; historical April baseline.
resource: planning/database/NEXT_STEPS.md
tags: [docs, planning, next-steps]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
---

# Database Refactor: Remaining Next Steps

## Current next work (2026-10-12)

PostgreSQL is the runtime database; Firebird-specific steps below are history.
The canonical initializer is `modules/db_schema/` through `modules/db_postgres.py`,
and deployed changes use Alembic revisions. The GitHub Project board is the
canonical queue; this document is a dependency/verification guide.

1. Reconcile the live migration revision with current DDL before choosing schema
   work. The initializer still declares `images.keywords`; the old v7.0/July
   removal date did not establish a completed migration. Coordinate readers,
   fallback/dual-write removal and gallery compatibility before hard removal.
2. Verify normalized keyword updates preserve their source/provenance and
   hand-added keywords. PR #594 delivered species refresh behavior; it did not
   fix every keyword overwrite path or perform a production refresh. Snapshot
   the approved cohort and take a verified backup before any rollout write.
3. Keep localization selections separate from storage/fusion work: 4,401
   large/medium selections are authoritative projections, while small-crop
   species fails its gate (0.8123 < 0.85). Region-score storage/fusion remains
   under #409 and must preserve full-frame completeness and gallery contracts.
4. Reconcile embedding consolidation against revisions 0004/0012/0024/0026/0029
   and [embedding next steps](../../features/planned/embeddings/NEXT_STEPS.md).
   Do not recreate the retired `images.image_embedding` storage or reserve
   historical migration numbers for proposed tables.
5. Use the [optimization roadmap](POSTGRES_SCHEMA_OPTIMIZATIONS.md) for remaining
   proposals; choose work from the board and verify it against current code.

See [the current operational handoff](../../../NEXT_STEPS.md) and
[the final localization gates](../../reports/localization-agent-panel-gates-2026-10-12.md).
No schema change, data cleanup or live migration was performed by this doc refresh.

## April baseline (historical)
- **Phase 1 (Integrity):** ✅ Complete.
- **Phase 2 (Normalization):** ✅ Complete.
  - `update_image_field` now calls `_sync_image_keywords` for keyword updates.
  - `_backfill_image_xmp` implemented (runs at startup for remaining images).
- **Phase 3 (Query Refactor):** ✅ Complete.
  - All 6 `keywords LIKE ?` locations replaced with `EXISTS` on `IMAGE_KEYWORDS`/`KEYWORDS_DIM`.
  - New `_add_keyword_filter()` helper centralizes the pattern.
- **Phase 4 (Validation & Cleanup):** ✅ **4a–4c complete** on the Python side (primary reads, soft-deprecation logging); **4d** (hard removal of legacy `IMAGES.KEYWORDS`) scheduled for v7.0 (July 2026). See [PHASE4_KEYWORDS_HUB.md](PHASE4_KEYWORDS_HUB.md), [PHASE4_STATUS_SUMMARY.md](PHASE4_STATUS_SUMMARY.md), [DB_STATUS_REPORT.md](DB_STATUS_REPORT.md).
- **Phase 5 (PostgreSQL Optimizations):** 🔲 Planned — **high-priority** items include embedding storage consolidation and status integrity constraints; see [POSTGRES_SCHEMA_OPTIMIZATIONS.md](POSTGRES_SCHEMA_OPTIMIZATIONS.md).

---

## Phase 4: Remaining work (ongoing + scheduled)

**Done (Python / catalog):** consistency scripts, performance benchmarks, keyword discovery via `KEYWORDS_DIM`, primary read cutover, soft-deprecation warnings (Phases 4a–4c).

**Ongoing / optional verification:** spot-checks that sampled rows stay in parity; large-corpus keyword search latency checks; manual WebUI/API keyword edits when upgrading deployments.

**Still requires a gated migration:** Phase **4d** — remove writable/legacy
`IMAGES.KEYWORDS` only after reader/write and Electron compatibility verification.
The original v7.0 date is historical, not a current deadline. Coordinate with
[AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md) before hard removal.

---

## Verification Plan
1. **Manual Test:** Update an image keyword via WebUI/API and verify changes in both `IMAGES` and `IMAGE_KEYWORDS` tables.
2. **SQL Audit:** Run `SELECT COUNT(*) FROM IMAGE_KEYWORDS` to verify population.
3. **XMP Coverage:** Run `SELECT COUNT(*) FROM images i LEFT JOIN image_xmp x ON i.id = x.image_id WHERE x.image_id IS NULL AND (i.rating IS NOT NULL OR i.keywords IS NOT NULL)` — should return 0.
4. **Performance Test:** Execute a keyword search with 50,000+ images and measure latency improvements.

---

## Related: PostgreSQL and migration history

The normalized `IMAGE_KEYWORDS` / `KEYWORDS_DIM` / `IMAGE_XMP` tables exist in the Postgres
schema (`modules/db_postgres.py` `init_db()`).

See [`FIREBIRD_POSTGRES_MIGRATION.md`](FIREBIRD_POSTGRES_MIGRATION.md) for full history. The
Python backend is **PostgreSQL-native**; Firebird runtime and dual-write were decommissioned.
Legacy translation helpers behind the `modules/db/` facade remain **SQL dialect helpers**
for legacy Firebird-style queries routed through the Postgres adapter — it is not a
dual-write gate.

**Electron / gallery:** The desktop app uses PostgreSQL (or backend `api` SQL mode); legacy Firebird runtime in the gallery is removed. Coordinate **normalized keyword** query shapes and any schema contract changes with [`AGENT_COORDINATION.md`](../../technical/AGENT_COORDINATION.md), especially ahead of Phase **4d** (legacy column removal).

---

## New Horizon: PostgreSQL Native Optimizations

With the primary migration to PostgreSQL complete, the focus shifts to native optimizations (JSONB, Vector tuning, the status fact table, etc.). 

See the detailed **[PostgreSQL Optimization Roadmap](POSTGRES_SCHEMA_OPTIMIZATIONS.md)** for more details.
