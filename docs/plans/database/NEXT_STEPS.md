# Database Refactor: Remaining Next Steps

Based on the audit of `modules/db.py` and the existing implementation guides, here are the concrete next steps to complete Phases 2 and 3 of the database refactor.

## Current Status (Audit Summary)
- **Phase 1 (Integrity):** Complete.
- **Phase 2 (Normalization):** 
    - Tables `KEYWORDS_DIM`, `IMAGE_KEYWORDS`, and `IMAGE_XMP` exist.
    - `upsert_image` correctly performs dual-write sync for keywords.
    - `update_image_field` is **MISSING** keyword sync.
    - `_backfill_keywords` is implemented but needs healthy verification.
    - `_backfill_image_xmp` is a **STUB** and needs implementation.
- **Phase 3 (Query Refactor):**
    - `get_images_paginated_with_count` and other query functions still use legacy `LIKE` scans on the `IMAGES` table.

---

## Next Steps

### Phase 2: Completion
1. **[MODIFY] [db.py](file:///d:/Projects/image-scoring/modules/db.py)**
    - Add `_sync_image_keywords` call to `update_image_field` when the `keywords` field is updated.
    - Implement `_backfill_image_xmp`: Loop through `IMAGES` and populate `IMAGE_XMP` with `rating`, `label`, `keywords`, `title`, and `description`.
    - Verify `_backfill_keywords` execution and data integrity.

### Phase 3: Query Refactoring
1. **[MODIFY] [db.py](file:///d:/Projects/image-scoring/modules/db.py)**
    - Refactor `get_images_paginated_with_count` to use `EXISTS` on `IMAGE_KEYWORDS` for keyword filtering instead of `LIKE` on `IMAGES.KEYWORDS`.
    - Refactor `get_filtered_paths` similarly.
    - Refactor any other keyword-based search functions.
2. **[Refactor] Keyword Discovery**
    - Change keyword discovery logic to query `KEYWORDS_DIM` directly instead of scanning the `IMAGES` table.

### Phase 4: Validation & Cleanup
1. **Data Consistency Check:** Run scripts to ensure `IMAGES` data matches `IMAGE_KEYWORDS` and `IMAGE_XMP`.
2. **Performance Benchmarking:** Verify that keyword scans now complete in <150ms.
3. **Deprecation Plan:** Prepare to switch primary reads/writes to normalized tables in a future cycle.

---

## Verification Plan
1. **Manual Test:** Update an image keyword via WebUI/API and verify changes in both `IMAGES` and `IMAGE_KEYWORDS` tables.
2. **SQL Audit:** Run `SELECT COUNT(*) FROM IMAGE_KEYWORDS` before and after running the backfill.
3. **Performance Test:** Execute a keyword search with 50,000+ images and measure latency improvements.
