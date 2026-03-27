# Abstraction Layers — Implementation Plan

> See also: [DB_CONNECTOR.md](DB_CONNECTOR.md) — full design reference for the connector layer.

## Goal

Introduce a `DbClient` abstraction so scoring/pipeline modules no longer `import db` directly. This enables:
1. Running the monolith as-is (local mode — `DbClientLocal` delegates to `db.py`)
2. Future split into separate services (HTTP mode — `DbClientHttp` calls a DB API service)

---

## Current State — Dependency Map

The following modules directly `from modules import db`:

### Scoring-side modules (would move to Scoring Service)
| Module | `db.*` functions used |
|---|---|
| `scoring.py` | `backup_database`, `create_job`, `delete_image`, `get_db`, `get_image_details`, `get_incomplete_records`, `update_job_status` |
| `pipeline.py` | `get_image_details`, `set_image_phase_status`, `upsert_image` |
| `engine.py` | `check_and_update_folder_status`, `is_folder_scored` |
| `tagging.py` | `check_and_update_folder_keywords_status`, `create_job`, `get_all_images`, `get_db`, `get_image_details`, `get_images_by_folder`, `get_images_for_tag_propagation`, `set_image_phase_status`, `update_image_field`, `update_image_fields_batch`, `update_job_status` |
| `clustering.py` | `clear_cluster_progress`, `clear_stacks_in_folder`, `create_stacks_batch`, `get_all_folders`, `get_all_images`, `get_clustered_folders`, `get_image_details`, `get_image_phase_statuses`, `get_images_by_folder`, `get_stack_count`, `mark_folder_clustered`, `set_image_phase_status`, `update_image_embeddings_batch`, `update_image_field`, `update_job_status` |
| `culling.py` | `add_images_to_culling_session`, `create_culling_session`, `get_culling_session`, `get_images_by_folder`, `get_session_groups`, `get_session_picks`, `get_session_stats`, `get_stack_count_for_folder`, `get_stack_ids_for_image_ids`, `set_best_in_group`, `set_pick_decision`, `update_culling_session` |
| `bird_species.py` | `create_job`, `get_db`, `get_images_with_keyword`, `update_image_fields_batch`, `update_job_status` |
| `indexing_runner.py` | `create_job`, `get_all_images`, `get_image_by_hash`, `get_image_details`, `get_image_phase_status`, `register_image_path`, `set_image_phase_status`, `update_job_status`, `upsert_image` |
| `metadata_runner.py` | `create_job`, `generate_image_uuid`, `get_all_images`, `get_image_details`, `get_image_phase_status`, `get_images_by_folder`, `set_image_phase_status`, `update_image_uuid`, `update_job_status` |
| `selection_runner.py` | `create_job`, `create_job_phases`, `enqueue_job`, `get_images_by_folder`, `get_job_phases`, `set_image_phase_status`, `set_job_phase_state`, `update_job_status` |
| `selection.py` | `batch_update_cull_decisions`, `get_all_folders`, `get_image_embeddings_batch`, `get_images_by_folder` |
| `selector_resolver.py` | `get_db`, `get_or_create_folder`, `sync_folder_to_db` |
| `phases_policy.py` | `get_image_phase_statuses` |
| `job_dispatcher.py` | `dequeue_next_job`, `get_queued_jobs`, `update_job_status` |
| `pipeline_orchestrator.py` | `create_job`, `create_job_phases`, `get_all_phases`, `get_folder_phase_summary`, `get_interrupted_jobs`, `get_job_by_id`, `get_job_phases`, `get_next_running_job_phase`, `recover_running_jobs`, `set_folder_phase_status`, `set_job_execution_cursor`, `set_job_phase_state`, `update_job_status` |

**Total: ~60 unique `db.*` functions across 15 modules.**

---

## Proposed Changes

### Phase 0: DbConnector Package ✅ DONE (2026-03-26)

Transport-layer abstraction beneath `db.py`. See [DB_CONNECTOR.md](DB_CONNECTOR.md) for full design.

- `modules/db_connector/protocol.py` — `IConnector` + `ITransaction` Protocol
- `modules/db_connector/firebird.py` — FirebirdConnector (wraps `db.get_db()`)
- `modules/db_connector/postgres.py` — PostgresConnector (wraps `db_postgres.py` pool)
- `modules/db_connector/api.py` — ApiConnector (HTTP proxy to `/api/db/query`)
- `modules/db_connector/factory.py` — singleton; `database.engine` config key
- `modules/api_db.py` — added `GET /api/db/ping`, `POST /api/db/query`, `POST /api/db/transaction`
- 5 functions migrated in `db.py` as proof-of-concept
- 33 unit tests (no DB required)

---

### Phase 1: DbClient Package ✅ DONE

#### [NEW] `modules/db_client/__init__.py`
Re-exports `get_db_client()` and `DbClientProtocol`.

#### [NEW] `modules/db_client/protocol.py`
`DbClientProtocol` — typing.Protocol with ~60 methods grouped by domain:
- Image CRUD (18 methods)
- Phase tracking (3 methods)
- Job management (15 methods)
- Folder operations (10 methods)
- Stacks/clustering (6 methods)
- Culling sessions (10 methods)
- Utilities (3 methods)

#### [NEW] `modules/db_client/local.py`
`DbClientLocal` — delegates every call to `modules.db`. Uses lazy import via `@property` to avoid circular imports.

#### [NEW] `modules/db_client/http.py`
`DbClientHttp` — full HTTP client using `requests`. Each method maps to a REST endpoint with:
- Proper 404 handling (returns `None` instead of raising)
- Configurable timeouts (30s default, 120s for batch ops)
- JSON serialization for enum values (phase codes, statuses)

#### [NEW] `modules/db_client/factory.py`
Thread-safe singleton factory. Reads `database.client_mode` from config (`"local"` or `"http"`).

---

### Phase 2: API Router Split (Future)

Split `api.py` (5300 LOC) into focused sub-routers:

#### [NEW] `modules/api_db.py`
DB-facing endpoints: images, folders, stacks, jobs, stats, export.

#### [NEW] `modules/api_scoring.py`
Scoring-facing endpoints: scoring/tagging/clustering start/stop/status.

#### [MODIFY] `modules/api.py`
Thin shim that includes both sub-routers (backward-compatible).

---

### Phase 3: Refactor Runners (Future)

Update each scoring-side module to accept a `DbClient` via dependency injection instead of importing `db` directly. Example pattern:

```python
# Before:
from modules import db
class ScoringRunner:
    def start(self):
        job_id = db.create_job(...)

# After:
from modules.db_client import get_db_client
class ScoringRunner:
    def __init__(self, db_client=None):
        self._db = db_client or get_db_client()
    def start(self):
        job_id = self._db.create_job(...)
```

---

## Verification Plan

### Automated Tests
- Existing tests must continue passing (monolith unchanged)
- New unit tests for `DbClientLocal` delegation
- Integration tests for `DbClientHttp` against running DB API

### Manual Verification
- Start WebUI normally → all functions work identically
- Config `database.client_mode = "local"` is the default
