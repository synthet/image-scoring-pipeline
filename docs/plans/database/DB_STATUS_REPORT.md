# Database Refactor Status Report

**Date:** 2026-03-10
**Current Target:** Phase 3 — Query Refactoring

## Executive Summary
Phase 1 (Integrity & Hardening) and Phase 2 (Normalization) are **substantially complete** at the database level. The normalized tables exist and are populated. However, **Phase 3 (Query Refactoring) has not yet been implemented in the application code**, meaning the performance benefits of normalization are not yet being realized.

---

## Phase 1: Integrity + Index Hardening
**Status:** ✅ COMPLETED

| Task | Status | Evidence |
|------|--------|----------|
| Add `UQ_IMAGES_FILE_PATH` | ✅ | Unique index exists in DB. |
| Add `UQ_IMAGES_IMAGE_UUID`| ✅ | Unique index exists in DB. |
| Add Composite Indexes | ✅ | `IDX_IMAGES_FOLDER_SCORE` and `IDX_IMAGES_STACK_SCORE` are present. |
| Remove Redundant Indexes | ✅ | `IDX_IMAGES_FOLDER_ID` and `IDX_IMAGES_STACK_ID` have been dropped. |
| Repair Orphan Stacks | ✅ | Database health check reports no integrity issues. |

---

## Phase 2: Hybrid 3NF Normalization
**Status:** 🏃 IN PROGRESS (Schema done, Backfill partial)

- **Keywords:**
  - `KEYWORDS_DIM` & `IMAGE_KEYWORDS` created. ✅
  - **Backfill:** ~60,200 links created. Population looks healthy for 45,617 images.
- **Metadata (XMP):**
  - `IMAGE_XMP` created. ✅
  - **Backfill:** 35,343 records present (approx. 77% coverage). About 10,000 images still need `IMAGE_XMP` records if they have metadata in the main `IMAGES` table.
- **Stack Cache:**
  - `STACK_CACHE` created and has 8,500 records. ✅

> [!IMPORTANT]
> No DB triggers were found for `IMAGE_KEYWORDS` or `IMAGE_XMP` synchronization. The system currently relies on the application layer (`modules/db.py`) to manage dual-writes.

---

## Phase 3: Query Refactor in App
**Status:** ❌ NOT STARTED

The application code (`modules/db.py`) is still using legacy BLOB search for keywords:
- `get_image_count()` still uses `keywords LIKE ?` (Line 527)
- `get_images_paginated()` still uses `keywords LIKE ?` (Line 619)
- `get_images_paginated_with_count()` still uses `keywords LIKE ?` (Line 746)

---

## Next Recommended Steps

1. **Complete Phase 2 Backfill:** Ensure all 45,617 images have corresponding `IMAGE_XMP` records if they possess metadata.
2. **Implement Phase 3:** Refactor `get_image_count`, `get_images_paginated`, and `get_images_paginated_with_count` to use `EXISTS (SELECT 1 FROM IMAGE_KEYWORDS ...)` instead of `LIKE` scans.
3. **Keyword Discovery Optimization:** Update the keyword cloud generation to query `KEYWORDS_DIM` instead of scanning the `IMAGES` table.
