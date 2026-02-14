---
name: firebird-db
description: Firebird database integration — connection, schema, queries, and SQL dialect differences.
---

# Firebird Database

The project uses **Firebird SQL** (via `firebird-driver`) for persistent storage of image scores, metadata, stacks, and job history. The database file is `SCORING_HISTORY.FDB` at the project root.

## Connection

All database access goes through `modules/db.py` → `get_db()`.

```python
from modules.db import get_db

conn = get_db()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM images")
count = cur.fetchone()[0]
conn.close()
```

### Connection Modes
- **Windows**: Embedded or TCP to `localhost:3050`
- **WSL / Docker**: Always TCP to the Windows host (e.g., `host.docker.internal:3050`)
- **CRITICAL**: Never access the `.FDB` file directly from WSL — use TCP only.

### Configuration
Database settings live in `config.json` → `database` section:
```json
{
  "database": {
    "filename": "SCORING_HISTORY.FDB",
    "user": "sysdba",
    "password": "masterkey"
  }
}
```

## Proxy Classes

`get_db()` returns a `FirebirdConnectionProxy` that mimics the `sqlite3` API:
- `FirebirdConnectionProxy` — wraps `firebird.driver.Connection`
- `FirebirdCursorProxy` — translates SQLite-style queries to Firebird dialect
- `RowWrapper` — makes rows accessible by column name (like `sqlite3.Row`)

The proxy auto-translates common SQLite patterns:
- `?` params → Firebird `?` (same)
- `LIMIT/OFFSET` → `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY`
- `CREATE TABLE IF NOT EXISTS` → conditional check
- `INSERT OR REPLACE` → `UPDATE OR INSERT ... MATCHING`

## Core Tables

### `images`
Primary table — one row per scored image.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Auto-generated |
| `file_path` | VARCHAR | Full path to image file |
| `file_hash` | VARCHAR | SHA-256 content hash |
| `score_general` | DOUBLE | Composite general score (0–1) |
| `score_technical` | DOUBLE | Composite technical score (0–1) |
| `score_aesthetic` | DOUBLE | Composite aesthetic score (0–1) |
| `score_spaq` | DOUBLE | Raw SPAQ score (normalized 0–1) |
| `score_ava` | DOUBLE | Raw AVA score (normalized 0–1) |
| `score_liqe` | DOUBLE | Raw LIQE score (normalized 0–1) |
| `score_koniq` | DOUBLE | Raw KonIQ score (normalized 0–1) |
| `score_paq2piq` | DOUBLE | Raw PaQ2PiQ score (normalized 0–1) |
| `rating` | INTEGER | Star rating (0–5) |
| `label` | VARCHAR | Color label (e.g., "green", "red") |
| `keywords` | BLOB | JSON array of auto-generated tags |
| `stack_id` | INTEGER | FK → stacks.id |
| `folder_id` | INTEGER | FK → folders.id |
| `date_taken` | TIMESTAMP | EXIF date |

### Other Tables
- `jobs` — batch processing job history
- `folders` — cached folder tree structure
- `stacks` — image grouping/clustering
- `culling_sessions` / `culling_picks` — culling workflow persistence

## Key Functions in `modules/db.py`

| Function | Purpose |
|----------|---------|
| `get_db()` | Open a Firebird connection (with proxy) |
| `init_db()` | Create/migrate schema |
| `get_images_paginated(...)` | Paginated image query with filters |
| `get_image_count(...)` | Count images matching filters |
| `upsert_image(...)` | Insert or update an image record |
| `get_or_create_folder(...)` | Ensure folder exists in folders table |

## Firebird SQL Gotchas

1. **No `AUTOINCREMENT`** — use generators/sequences
2. **No `CREATE TABLE IF NOT EXISTS`** — check `RDB$RELATIONS` first
3. **No `INSERT OR IGNORE`** — use `UPDATE OR INSERT ... MATCHING`
4. **String params**: Use `?` (same as SQLite), not `%s`
5. **Pagination**: Use `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` instead of `LIMIT/OFFSET`
6. **Functions**: `char_length()` not `length()`, `substring()` not `substr()`
7. **Case sensitivity**: Unquoted identifiers are uppercased by Firebird

## Schema Migrations

New columns are added in `_init_db_impl()` inside `get_db()`. Pattern:
```python
# Check if column exists before adding
cur.execute("SELECT 1 FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME='IMAGES' AND RDB$FIELD_NAME='NEW_COLUMN'")
if not cur.fetchone():
    cur.execute("ALTER TABLE images ADD new_column DOUBLE PRECISION DEFAULT 0")
    conn.commit()
```

## Running the Firebird Server

On Windows, start the bundled Firebird server:
```powershell
.\run_firebird.bat
```
This starts Firebird on port 3050, required for WSL/Docker access.
