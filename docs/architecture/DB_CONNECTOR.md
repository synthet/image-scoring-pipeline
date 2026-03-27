# DB Connector — Architecture & Design

> Status: **Implemented** — 2026-03-26
> Location: `modules/db_connector/`

---

## 1. Problem

`modules/db.py` (≈ 8 800 LOC; growing) contains both domain logic (SQL queries, business rules) and
raw connection management scattered across every function:

```python
# repeated in hundreds of functions
conn = get_db()          # open Firebird or Postgres connection
c = conn.cursor()
c.execute("SELECT ...", params)
row = c.fetchone()
conn.close()             # easy to forget
```

Engine-routing branches appear throughout:

```python
if _get_db_engine() == "postgres":
    db_postgres.execute_write("UPDATE ... SET col = %s WHERE id = %s", ...)
else:
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE ... SET col = ? WHERE id = ?", ...)
    conn.commit()
    conn.close()
```

Consequences:
- Adding a third backend (e.g. HTTP proxy) requires touching every function
- Connection leaks when exceptions skip `conn.close()`
- Testing requires a live database

---

## 2. Solution

`modules/db_connector/` is a **transport layer** that abstracts *how* SQL is executed, independent of *what* SQL to run.

### Architecture layers

```
┌──────────────────────────────────────────────────────────────┐
│  Callers (api.py, engine.py, scoring.py, …)                  │
└──────────────────────┬───────────────────────────────────────┘
                       │ domain calls
┌──────────────────────▼───────────────────────────────────────┐
│  modules/db_client/  (DbClientProtocol)                      │
│  60+ named methods: get_image_details(), create_job(), …     │
│  Modes: "local" → db.py  |  "http" → REST API               │
└──────────────────────┬───────────────────────────────────────┘
                       │ uses
┌──────────────────────▼───────────────────────────────────────┐
│  modules/db.py  (SQL queries + domain logic)                 │
└──────────────────────┬───────────────────────────────────────┘
                       │ get_connector()
┌──────────────────────▼───────────────────────────────────────┐
│  modules/db_connector/  (IConnector — transport)  ← NEW     │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────────┐  │
│  │ FirebirdConn.   │ │ PostgresConn.    │ │ ApiConn.     │  │
│  │ (default)       │ │ (psycopg2 pool)  │ │ (HTTP proxy) │  │
│  └─────────────────┘ └──────────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Key separation:**
- `db_connector/` answers *"how do I send SQL to the database?"*
- `db.py` answers *"what SQL do I run for this domain operation?"*
- `db_client/` answers *"what domain operation does the caller need?"*

---

## 3. Interface

```python
from modules.db_connector import get_connector

# Simple SELECT — returns list[dict]
rows = get_connector().query(
    "SELECT * FROM images WHERE folder_id = ?", (folder_id,)
)

# Single-row SELECT — returns dict | None
image = get_connector().query_one(
    "SELECT * FROM images WHERE id = ?", (image_id,)
)

# INSERT/UPDATE/DELETE — returns rowcount
n = get_connector().execute(
    "UPDATE images SET rating = ? WHERE id = ?", (5, image_id)
)

# INSERT … RETURNING — returns list[dict]
rows = get_connector().execute_returning(
    "INSERT INTO jobs (input_path, status) VALUES (?, ?) RETURNING id",
    (path, "queued"),
)
job_id = rows[0]["id"]

# Batch write
get_connector().execute_many(
    "UPDATE images SET label = ? WHERE id = ?",
    [(label, img_id) for img_id, label in updates],
)

# Atomic multi-statement transaction
def _enqueue(tx):
    rows = tx.execute_returning(
        "INSERT INTO jobs (...) VALUES (?) RETURNING id", (...)
    )
    job_id = rows[0]["id"]
    tx.execute("UPDATE jobs SET queue_position = ? WHERE id = ?", (job_id, job_id))
    return job_id

job_id = get_connector().run_transaction(_enqueue)

# Connectivity probe
if not get_connector().check_connection():
    raise RuntimeError("Database unavailable")
```

### SQL dialect

All callers write **Firebird SQL** with `?` placeholders:

```sql
SELECT * FROM images WHERE image_hash = ?
INSERT INTO jobs (...) VALUES (?, ?, ?) RETURNING id
UPDATE OR INSERT INTO image_exif (...) VALUES (?) MATCHING (image_id)
```

`PostgresConnector` translates automatically via `db._translate_fb_to_pg()`:
- `?` → `%s`
- `UPDATE OR INSERT … MATCHING` → `INSERT … ON CONFLICT DO UPDATE`
- `SELECT FIRST n` → `SELECT … LIMIT n`
- `DATEDIFF(UNIT FROM a TO b)` → `EXTRACT(…)`
- `LIST(col, sep)` → `STRING_AGG(col, sep)`

---

## 4. Implementations

### 4.1 FirebirdConnector (default)

File: [`modules/db_connector/firebird.py`](../../modules/db_connector/firebird.py)

Delegates to `modules.db.get_db()` (lazily imported to avoid circular imports).

- Each `query()` / `execute()` call opens one `FirebirdConnectionProxy`, runs, closes
- `run_transaction()` opens **one** connection, passes a `_FbTx` context to the callback,
  commits on normal return, rolls back on exception
- `execute()` returns `affected_rows` from the Firebird cursor
- Dual-write to PostgreSQL happens transparently inside `FirebirdCursorProxy` (existing behaviour)

```python
class FirebirdConnector:
    type = 'firebird'

    def query(self, sql, params=None) -> list[dict]:
        conn = self._get_conn()   # db.get_db()
        try:
            c = conn.cursor()
            c.execute(sql, tuple(params) if params else None)
            return [dict(r) for r in c.fetchall()]
        finally:
            conn.close()
```

### 4.2 PostgresConnector

File: [`modules/db_connector/postgres.py`](../../modules/db_connector/postgres.py)

Wraps the psycopg2 pool managed by `modules.db_postgres`.

- `query()` → `db_postgres.execute_select(translated_sql, params)`
- `execute()` → `db_postgres.execute_write(translated_sql, params)`
- `execute_returning()` → uses `PGConnectionManager(commit=True)` + `RealDictCursor`
- `run_transaction()` → single `PGConnectionManager` with manual commit/rollback

SQL is translated from Firebird dialect before execution via `_translate()`.

### 4.3 ApiConnector

File: [`modules/db_connector/api.py`](../../modules/db_connector/api.py)

Proxies SQL to `POST /api/db/query` on a remote backend URL.
Intended for scoring workers or external clients that need DB access without a
direct driver connection. When `database.query_token` is set, mutating calls
include the `X-DB-Write-Token` header (same contract as `api_db.py`).

```
query()             → POST /api/db/query  { sql, params, write: false }
execute()           → POST /api/db/query  { sql, params, write: true }
execute_returning() → POST /api/db/query  { sql, params, write: true }
run_transaction()   → POST /api/db/transaction  { statements: [...] }
check_connection()  → GET  /api/db/ping
```

**Transaction semantics note:** `run_transaction` collects write statements during the
callback and sends them as an atomic batch to `/api/db/transaction`. Read operations
inside the callback (`query()`) execute immediately (non-transactionally). For full
ACID transactions, use `FirebirdConnector` or `PostgresConnector` directly.

---

## 5. Factory

File: [`modules/db_connector/factory.py`](../../modules/db_connector/factory.py)

Thread-safe singleton (double-checked locking, same pattern as `db_client/factory.py`).

```python
from modules.db_connector import get_connector

connector = get_connector()   # returns cached singleton
```

Selection is driven by `database.engine` in `config.json`:

| `database.engine` | Implementation | When to use |
|---|---|---|
| `"firebird"` (default) | `FirebirdConnector` | Normal monolith operation |
| `"postgres"` | `PostgresConnector` | PostgreSQL primary mode |
| `"api"` | `ApiConnector` | Remote process or Electron app |

Additional config keys (under `database`):

| Key | Default | Used by |
|-----|---------|---------|
| `api_url` | `"http://localhost:7860"` | `ApiConnector` base URL |
| `query_token` | `""` | Write auth token for `/api/db/query`; empty = writes blocked |

Use `reset_connector()` to clear the singleton (e.g. in tests or after config reload).

---

## 6. API Endpoints

Added to [`modules/api_db.py`](../../modules/api_db.py) — served on the main FastAPI router.

### `GET /api/db/ping`

Connectivity probe. Returns the active engine name.

```json
{ "ok": true, "engine": "firebird" }
```

### `POST /api/db/query`

Execute a SQL statement (read or write).

**Request body:**
```json
{
  "sql":         "SELECT * FROM images WHERE id = ?",
  "params":      [42],
  "write":       false,
  "executemany": false
}
```

**Response:**
```json
{ "rows": [{ "id": 42, "file_path": "..." }], "rowcount": 1 }
```

**Auth:** Read queries require no authentication. Write queries (`"write": true`) require
the `X-DB-Write-Token` header to match `config.database.query_token`. If the token is
empty/unset, writes are blocked with HTTP 403.

### `POST /api/db/transaction`

Execute a batch of write statements atomically.

**Request body:**
```json
{
  "statements": [
    { "sql": "UPDATE jobs SET status = ? WHERE id = ?", "params": ["done", 1] },
    { "sql": "INSERT INTO job_phases (...) VALUES (?)", "params": [...] }
  ]
}
```

**Response:** `{ "ok": true, "count": 2 }`

Requires `X-DB-Write-Token`.

---

## 7. Migration in `db.py`

`db.py` exposes a thin shim:

```python
def get_connector():
    from modules.db_connector import get_connector as _gc
    return _gc()
```

Five functions were migrated as the initial proof-of-concept, removing the per-function
`if _get_db_engine() == "postgres":` branch entirely:

| Function | Migration type |
|---|---|
| `get_image_by_hash()` | Removed engine-routing branch → `connector.query_one()` |
| `get_image_details()` | Removed engine-routing branch → `connector.query_one()` |
| `update_image_field()` | Removed engine-routing branch → `connector.execute()` |
| `create_job()` | Removed explicit connection mgmt → `connector.execute_returning()` |
| `enqueue_job()` | Multi-step → `connector.run_transaction()` |

**Before (update_image_field):**
```python
if _get_db_engine() == "postgres":
    db_postgres.execute_write(f"UPDATE images SET {field_name} = %s WHERE id = %s", ...)
else:
    conn = get_db()
    c = conn.cursor()
    c.execute(f"UPDATE images SET {field_name} = ? WHERE id = ?", ...)
    conn.commit()
    conn.close()
```

**After:**
```python
get_connector().execute(
    f"UPDATE images SET {field_name} = ? WHERE id = ?", (value, image_id)
)
```

The remaining ~60 functions still use the older `_get_db_engine()` branching pattern (calling
`db_postgres` helpers directly on the Postgres path). Migrating them to `get_connector()` is
a follow-on cleanup task that can proceed incrementally — both patterns work correctly today.

**Routing patterns currently in use (both correct):**

| Pattern | Example | Notes |
|---|---|---|
| `get_connector().query()` | `get_image_by_hash` | Preferred — engine-agnostic |
| `if _get_db_engine() == "postgres": db_postgres.execute_select(…)` | `get_all_paths` | Legacy — still correct, more verbose |

---

## 8. Testing

File: [`tests/test_db_connector.py`](../../tests/test_db_connector.py)

35 unit tests, **no live database required** (all mocked). Postgres delegation tests stub
`modules.db_postgres` via `sys.modules` so they run when `psycopg2` is not installed:

| Test class | What is tested |
|---|---|
| `TestIConnectorProtocol` | Protocol structure, runtime isinstance checks |
| `TestFactory` | Engine selection, singleton, thread safety, reset |
| `TestFirebirdConnector` | query, query_one, execute, execute_returning, run_transaction, check_connection |
| `TestApiConnector` | HTTP endpoint calls, run_transaction batch, close |
| `TestPostgresConnector` | Delegation to db_postgres helpers |

Run:
```bash
python -m pytest tests/test_db_connector.py -v
```

---

## 9. Adding a New Backend

Implement the `IConnector` protocol (structural — no inheritance required):

```python
# modules/db_connector/my_backend.py
class MyConnector:
    type = 'mydb'

    def query(self, sql, params=None) -> list[dict]: ...
    def query_one(self, sql, params=None) -> dict | None: ...
    def execute(self, sql, params=None) -> int: ...
    def execute_returning(self, sql, params=None) -> list[dict]: ...
    def execute_many(self, sql, params_list) -> None: ...
    def run_transaction(self, callback) -> Any: ...
    def check_connection(self) -> bool: ...
    def verify_startup(self) -> bool: ...
    def close(self) -> None: ...
```

Then add a branch to `factory.py`:

```python
elif engine == "mydb":
    from modules.db_connector.my_backend import MyConnector
    _instance = MyConnector()
```

And set `database.engine = "mydb"` in `config.json`.

---

## 10. Relationship to `db_client/`

`db_client/` and `db_connector/` are at different levels of abstraction and coexist:

| | `db_connector/` | `db_client/` |
|---|---|---|
| **Level** | Transport (how to run SQL) | Domain API (what operation to do) |
| **Interface** | `query(sql, params)` | `get_image_details(file_path)` |
| **Users** | `db.py` internally | `api.py`, `engine.py`, runners |
| **Config key** | `database.engine` | `database.client_mode` |
| **Modes** | `firebird` / `postgres` / `api` | `local` / `http` |

`db_client/` uses `db.py` (which uses `db_connector/`) in local mode, or calls the REST
API directly in HTTP mode (bypassing both `db.py` and `db_connector/`).
