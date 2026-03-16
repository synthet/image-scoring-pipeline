# Database Refactor: Remaining Next Steps

## Current Status (as of 2026-03-11)
- **Phase 1 (Integrity):** ✅ Complete.
- **Phase 2 (Normalization):** ✅ Complete.
  - `update_image_field` now calls `_sync_image_keywords` for keyword updates.
  - `_backfill_image_xmp` implemented (runs at startup for remaining images).
- **Phase 3 (Query Refactor):** ✅ Complete.
  - All 6 `keywords LIKE ?` locations replaced with `EXISTS` on `IMAGE_KEYWORDS`/`KEYWORDS_DIM`.
  - New `_add_keyword_filter()` helper centralizes the pattern.

---

## Next Steps

### Phase 4: Validation & Cleanup
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
