# Firebird on Windows: sort temp directory (`fb_sort_*` errors)

## Symptom

Queries that need a large sort (for example `ORDER BY` over many rows) fail with:

`Sort error, I/O error for file "…\Firebird\temp\fb_sort_…", Error while trying to create file`  
(gdscode **335544675**)

## Cause

The Firebird server writes temporary sort files under **`TempDirectories`** in `Firebird/firebird.conf`. If that path is missing, not writable, or points at an **old clone path** (for example after renaming `image-scoring` → `image-scoring-backend`), the engine cannot create `fb_sort_*` files.

## Fix

1. Open `Firebird/firebird.conf` next to `firebird.exe` (used by `run_firebird.bat`).
2. Set **`TempDirectories`** to a directory that exists and is writable:
   - **Explicit (safest after renaming the repo folder):** e.g. `TempDirectories = D:/Projects/image-scoring-backend/Firebird/temp`  
     Use forward slashes; point at **`Firebird\temp`** under your **current** backend root — not an old path like `d:\Projects\image-scoring\…` if that folder no longer exists.
   - **Portable:** `TempDirectories = temp` — resolved relative to this Firebird install directory (the folder that contains `firebird.exe`).
3. Ensure the **`Firebird\temp`** folder exists (`run_firebird.bat` creates it).
4. **Restart** the Firebird process so the new setting is loaded. Until you restart, the server keeps the **old** `TempDirectories` value (you will still see errors mentioning the previous path, e.g. `d:\Projects\image-scoring\Firebird\temp`, even after you edit the file on disk).

### If the error still names `d:\Projects\image-scoring\…`

That path is almost always the **previous** config still in memory, or a second Firebird started from an old copy. Stop **all** `firebird.exe` instances, confirm `firebird.conf` uses your real backend path, then start **`image-scoring-backend\run_firebird.bat`** again.

## Related

- Windows launcher: `run_firebird.bat` (application mode, port 3050).
