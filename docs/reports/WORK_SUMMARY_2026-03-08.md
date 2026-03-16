# Work Summary — 2026-03-08

Summary of changes made in this session across the image-scoring and electron-image-scoring projects.

---

## 1. Import via API with DB Fallback

**Goal:** Use the Gradio backend for import when available; fall back to direct Firebird DB when not.

### Python Backend (`image-scoring`)

| File | Change |
|------|--------|
| `modules/db.py` | Added `find_image_id_by_path()`, `find_image_id_by_uuid()`, `register_image_for_import()` |
| `modules/api.py` | Added `ImportRegisterRequest` model and `POST /api/import/register` endpoint |

### Electron App (`electron-image-scoring`)

| File | Change |
|------|--------|
| `electron/apiTypes.ts` | Added `ImportRegisterRequest`, `ImportRegisterResponse` |
| `electron/apiService.ts` | Added `importRegister()` |
| `electron/main.ts` | Updated `import:run` to try API first, then fall back to direct DB |

### Flow

1. `apiService.isAvailable()` checks if Gradio is reachable.
2. If available: `POST /api/import/register` with `folder_path`.
3. If unavailable or error: existing direct Firebird import logic.
4. API converts Windows paths to WSL only when the backend runs on Linux (WSL); when the backend runs natively on Windows, paths are kept as-is.

---

## 2. Path Handling (Windows vs WSL)

**Goal:** Correct path normalization for DB storage and WSL pass-through.

### Electron (`electron-image-scoring`)

| File | Change |
|------|--------|
| `electron/db.ts` | Updated `normalizePathForDb()` to pass through paths already in WSL format before `path.resolve()` to avoid mangling |

---

## 3. Prevent Duplicate Images by Image UUID

**Goal:** Avoid duplicate image records when the same image (same EXIF `ImageUniqueID`) appears at different paths.

### Python Backend (`image-scoring`)

| File | Change |
|------|--------|
| `modules/db.py` | **`upsert_image()`:** Before `UPDATE OR INSERT`, derive `image_uuid` from metadata; if it exists in DB with a different path, update that record instead of inserting |
| `modules/db.py` | **Schema migration:** Added `CREATE UNIQUE INDEX uq_images_image_uuid ON images(image_uuid)` (allows multiple NULLs) |

### Behavior

- **Same UUID, different path:** Existing record is updated with new path and scores; new path is registered in `file_paths`.
- **Same UUID, same path:** Normal `UPDATE OR INSERT` applies.
- **Unique index:** Enforces uniqueness at DB level; creation is skipped if duplicates already exist.

### Existing Checks (unchanged)

- Import API and Electron import already use `find_image_id_by_uuid` before inserting.
- Pipeline PrepWorker continues to use hash-based deduplication.

---

## Files Modified

### `image-scoring`

- `modules/db.py` — UUID dedup, import helpers, unique index
- `modules/api.py` — Import register endpoint

### `electron-image-scoring`

- `electron/db.ts` — Path normalization
- `electron/main.ts` — Import API-first flow
- `electron/apiService.ts` — `importRegister()`
- `electron/apiTypes.ts` — Import types

---

## Implementation Verification Report

### 1. Import via API with DB Fallback

| Component | Status | Notes |
|-----------|--------|-------|
| apiTypes.ts | OK | ImportRegisterRequest (folder_path), ImportRegisterResponse (success, message, data: added/skipped/errors) |
| apiService.ts | OK | importRegister() calls POST /api/import/register with LONG_TIMEOUT |
| main.ts | OK | import:run uses apiService.isAvailable() → API first → fallback to direct DB on error |
| Python api.py | OK | ImportRegisterRequest, POST /api/import/register, path conversion only when backend runs on Linux (utils.convert_path_to_wsl) |
| Python db.py | OK | find_image_id_by_path(), find_image_id_by_uuid(), register_image_for_import() |

Flow matches the design: API first, then direct Firebird import on failure or when the backend is unavailable.

### 2. Path Handling (Windows vs WSL)

| Component | Status | Notes |
|-----------|--------|-------|
| db.ts normalizePathForDb() | OK | Early return for WSL paths (`/mnt/[a-zA-Z]/`) before path.resolve() to avoid mangling |

### 3. Duplicate Prevention by Image UUID

| Component | Status | Notes |
|-----------|--------|-------|
| Electron fallback | OK | Uses findImageByUuid() before insert; skips if UUID exists |
| Python API | OK | Uses find_image_id_by_uuid() before register_image_for_import |
| db.ts | OK | findImageByUuid(), insertImage() with image_uuid |
| Python upsert_image | OK | Checks UUID before INSERT; updates existing record if found at different path |
| Unique index | OK | uq_images_image_uuid in Python schema; Electron enforces via API or fallback |

### 4. Minor Observations

- **API response format:** Electron uses `res?.data?.added`, `res?.data?.skipped`, `res?.data?.errors`; Python returns ApiResponse with `data={"added": ..., "skipped": ..., "errors": ...}`. Shapes match.
- **Regex for WSL paths:** `normalizePathForDb` uses `/^\/mnt\/[a-zA-Z]\//`. Paths like `/mnt/d/` are matched; `/mnt/d` (no trailing slash) are not. Acceptable for typical folder paths.
- **Progress reporting:** API import sends a single progress event after completion (total = added + skipped + errs.length). Direct DB fallback sends per-file progress. Behavior differs but is consistent with each path.

### Summary

All described changes are implemented and consistent across Electron and Python. No issues found that would block the described behavior.
