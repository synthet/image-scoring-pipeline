# Database Refactor: Remaining Next Steps

## Current Status (as of 2026-03-26)
- **Phase 1 (Integrity):** ✅ Complete.
- **Phase 2 (Normalization):** ✅ Complete.
  - `update_image_field` now calls `_sync_image_keywords` for keyword updates.
  - `_backfill_image_xmp` implemented (runs at startup for remaining images).
- **Phase 3 (Query Refactor):** ✅ Complete.
  - All 6 `keywords LIKE ?` locations replaced with `EXISTS` on `IMAGE_KEYWORDS`/`KEYWORDS_DIM`.
  - New `_add_keyword_filter()` helper centralizes the pattern.
- **Phase 4 (Validation & Cleanup):** 🔲 Pending (see below).

---

## Phase 4: Validation & Cleanup (current target)

1. **Data Consistency Check:** Run scripts to ensure `IMAGES.KEYWORDS` data matches `IMAGE_KEYWORDS` entries.
2. **Performance Benchmarking:** Verify that keyword search queries complete in <150ms with 50K+ images.
3. **Keyword Discovery Optimization:** Change keyword cloud generation to query `KEYWORDS_DIM` directly instead of scanning the `IMAGES` table.
4. **Deprecation Plan:** Prepare to switch primary reads/writes to normalized tables and deprecate `IMAGES.KEYWORDS` BLOB column.

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
The function `_translate_fb_to_pg()` in `modules/db.py` remains as a **SQL dialect helper**
for legacy Firebird-style queries routed through the Postgres adapter — it is not a
dual-write gate.

**Electron / gallery:** Until the gallery app migrates off Firebird (`electron/db.ts`),
coordinate any keyword-query or schema contract changes with
[`AGENT_COORDINATION.md`](../../technical/AGENT_COORDINATION.md).
