---
type: Feature Spec
title: "Remote GPU worker 02: worker protocol"
description: Lease and fencing SQL on image_phase_work_claims, the worker gateway API, the rendered and original input modes, config sync from the host, and version checks.
resource: docs/specs/remote-gpu-worker/02-worker-protocol.md
tags: [specs, remote-worker, protocol, postgres, api]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.2
status: proposed
---

# Remote GPU worker 02: worker protocol

**Epic:** #435 · **Hub:** [INDEX.md](INDEX.md) · **Milestones:** M1 (#437), M3 (#439), M4 (#440)

## Summary

Work items are rows in `image_phase_work_claims`, extended with lease columns.
- **Claiming:** the worker claims batches directly in Postgres with `FOR UPDATE SKIP LOCKED`.
- **Committing:** each result commit is fenced by `worker_id` and `status='running'`.
- **Images and config:** these come from a token-authenticated gateway that takes an `image_id`, never a path.

## Schema (migration `0036_remote_worker`, mirrored in `modules/db_postgres.py`)

### `image_phase_work_claims`: new columns

The table is at `modules/db_postgres.py:686`.

| Column | Type | Meaning |
|---|---|---|
| `executor` | `VARCHAR(10) NOT NULL DEFAULT 'local'` | `local` or `remote`. Local claims keep today's behaviour. |
| `worker_id` | `VARCHAR(64)` | The worker holding the lease. NULL while queued. |
| `lease_expires_at` | `TIMESTAMPTZ` | The reaper requeues the claim after this. |
| `heartbeat_at` | `TIMESTAMPTZ` | The last extension of the lease. |
| `attempts` | `SMALLINT NOT NULL DEFAULT 0` | Incremented on each lease. |
| `last_error` | `TEXT` | The last failure, truncated. |
| `input_mode` | `VARCHAR(10)` | `rendered` or `original`, as used. |

- **New index:** `idx_ipwc_remote_ready ON (phase_code, status, lease_expires_at) WHERE executor='remote'`.
- **Kept as is:** `uq_ipwc_open_image_phase`, which still prevents two open claims on the same image × phase.
- **Claim `status` values:** today's are `queued`, `running` and `released`; `release_claims_for_job` sets the last (`modules/phase_work_claims.py:215`). Remote claims add three terminal values: `done`, `failed` and `cancelled`. The open-claim index only covers `queued` and `running`, so the new values need no index change.

### `remote_workers`

```sql
CREATE TABLE remote_workers (
  worker_id       VARCHAR(64) PRIMARY KEY,
  hostname        VARCHAR(255),
  gpu_name        VARCHAR(255),
  vram_mb         INTEGER,
  capabilities    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- phases, model versions, input modes
  worker_version  VARCHAR(50),
  schema_version  VARCHAR(50),
  status          VARCHAR(20) NOT NULL DEFAULT 'online', -- online | draining | offline
  last_heartbeat  TIMESTAMPTZ,
  registered_at   TIMESTAMPTZ DEFAULT now()
);
```

The outbox table is specified in [03](03-xmp-outbox.md).

## Lease lifecycle

```text
queued ──lease──▶ running ──commit (fenced)──▶ done
   ▲                 │ ├──worker failure──▶ failed (last_error; reaper may requeue)
   └──reaper─────────┘ └──lease expired──▶ queued (attempts+1)   or ▶ failed after max_attempts
cancel: host sets status='cancelled'; worker checks before compute and before commit
```

### Claim a batch (worker)

```sql
UPDATE image_phase_work_claims c
SET status = 'running', worker_id = %(worker)s, attempts = c.attempts + 1,
    lease_expires_at = now() + %(ttl)s * interval '1 second', heartbeat_at = now()
WHERE c.id IN (
  SELECT id FROM image_phase_work_claims
  WHERE executor = 'remote' AND status = 'queued' AND phase_code = ANY(%(phases)s)
  ORDER BY job_id, id
  LIMIT %(n)s
  FOR UPDATE SKIP LOCKED
)
RETURNING c.id, c.job_id, c.image_id, c.phase_code;
```

- **Batch size:** set by `batch_size` in the worker config, 8–32 depending on VRAM and phase.
- **Phase filter:** the worker only claims phases listed in its `capabilities.phases`.

### Extend the lease (worker heartbeat, every `ttl/3`)

```sql
UPDATE image_phase_work_claims
SET lease_expires_at = now() + %(ttl)s * interval '1 second', heartbeat_at = now()
WHERE worker_id = %(worker)s AND status = 'running' AND id = ANY(%(ids)s);
```

The worker also updates `remote_workers.last_heartbeat`, through the gateway or directly in the DB.

### Commit a result (worker, one transaction per image × phase)

1. Write the result rows with the existing `modules.db` writers, for example `upsert_image` (`modules/db_legacy.py:8736`) or `update_image_embeddings_batch_for_space` (`:12995`).
2. Call `set_image_phase_status(image_id, phase, 'done', …)` (`modules/db_legacy.py:13984`). It records `executor_version` (the column is in `image_phase_status`, `modules/db_postgres.py:1044`).
3. `INSERT INTO xmp_sync_outbox … ON CONFLICT DO NOTHING`. See [03](03-xmp-outbox.md).
4. **The fence:**
   ```sql
   UPDATE image_phase_work_claims SET status='done', released_at=now()
   WHERE id=%(claim)s AND worker_id=%(worker)s AND status='running';
   ```
   If the row count isn't 1, **roll back**. That means the lease was lost, or the claim was cancelled or re-leased.

The fence is the last statement, so a lost lease never leaves partial results behind.

### Reaper (host, every 30 s)

```sql
UPDATE image_phase_work_claims
SET status = CASE WHEN attempts >= %(max)s THEN 'failed' ELSE 'queued' END,
    worker_id = NULL, lease_expires_at = NULL,
    last_error = COALESCE(last_error, 'lease expired')
WHERE executor='remote' AND status='running' AND lease_expires_at < now();
```

Terminal claims move `image_phase_status` to `failed` through the existing helpers. That keeps the run UI consistent.

## Worker gateway API (`/worker/*`, own port)

Every request carries `Authorization: Bearer <token>`. The host maps each token to a `worker_id`; tokens are stored hashed in `secrets.json` (`worker_gateway.tokens`). A bad or missing token gets 401. A known worker whose status is `offline` gets 403.

| Method and path | Purpose | Notes |
|---|---|---|
| `POST /worker/register` | Upsert the `remote_workers` row | Body: hostname, GPU, VRAM, capabilities, `worker_version`, `schema_version`. Response: accepted, or a reject reason such as a schema mismatch. |
| `POST /worker/heartbeat` | Update `last_heartbeat` and status | Optional; the worker may heartbeat through the DB instead. |
| `GET /worker/config` | The model and scoring config the worker must use | See [Config sync](#config-sync). |
| `GET /worker/images/{image_id}/rendition?purpose=inference\|thumbnail` | `rendered` mode | See below. |
| `GET /worker/images/{image_id}/original` | `original` mode | Streamed with `Content-Length` and `ETag`. Range requests are supported. |

A separate OpenAPI file (`docs/reference/api/worker-gateway.openapi.json`) describes the gateway, so the main-API `contract_check.py` (`scripts/ci/contract_check.py`) is unaffected.

## Input modes

The mode comes from `input_mode` in the worker config, with an optional per-phase `phase_input_modes`. The mode actually used is written to `claims.input_mode`.

### `rendered`: host-rendered JPEG

| `purpose` | Served file | Used by default for |
|---|---|---|
| `thumbnail` | The 512 px thumbnail (`thumbnails.generate_thumbnail`, `modules/thumbnails.py:711`). It must already exist, because metadata creates it. | `keywords`, `culling` embeddings |
| `inference` | Non-RAW files: the original bytes. RAW files: the full-size preview (`generate_preview`, `modules/thumbnails.py:800`), which uses the embedded JPEG or a rawpy decode. | `scoring`, `localization`, `bird_species` |

Response headers:
- `X-Decode-Route`: a `modules/rendition.py` `DecodeRoute` value (`:54`);
- `X-Orientation-Applied`: `true` or `false`;
- `X-Content-SHA256`;
- `ETag`;
- the pixel width and height.

The worker stores the decode route with its results, just as `localization.decode_route` does today (migration `0035`).

**Pros:** smaller transfers; no RAW toolchain on the worker; the same pixels as the host's own preview path.
**Cons:** the host's CPU does the RAW decode.

### `original`: file bytes

- The host streams the original bytes. RAW files arrive as NEF, CR3, ARW and so on.
- The worker decodes them with the same chain the host uses: exiftool, then rawpy, then ImageMagick, via `convert_raw_to_jpeg` and `open_image_for_ml` (`modules/thumbnails.py:489`). It records its own decode route.
- The worker image must therefore include exiftool and rawpy.

**Pros:** it offloads decoding from the host.
**Cons:** a RAW file is 25–60 MB; toolchain versions can make the decoded pixels differ (INDEX D-4); the worker image is bigger.

### Fetch cache (worker)

- **Keys and eviction:** an LRU on disk (`cache_dir`, `cache_max_gb`), keyed by `(image_id, sha256, purpose)`.
- **Revalidation:** by `ETag`, which gives a 304 when unchanged.
- **Reuse:** a multi-phase run (localization → scoring → bird_species) fetches each image once.
- **Temp files:** the models get a temp-file path inside the cache. They stay path-based: `IScoringModel.predict(image_path)`, `modules/engines/base.py:30`.

## Config sync

`GET /worker/config` returns only the sections that change model behaviour:
- `scoring.models`, `scoring.fusion`, `percentile_anchors`;
- `localization`, `bird_detection`;
- `tagging`, `clustering` (the embedding part only), `embeddings`;
- `raw_conversion`;
- a `config_hash`.

The worker loads these at startup, then re-fetches when a heartbeat response carries a different `config_hash`. Before it applies new config it finishes the items it holds, so no item mixes two configs.

**Never returned:** `database.*`, tokens, or anything read through `get_secret`.

The worker's own `worker.json` holds only local settings:
- `gateway_url`, `worker_id`;
- `input_mode`, `phase_input_modes`, `phases`;
- `batch_size`, `lease_ttl_seconds`;
- `cache_dir`, `cache_max_gb`.

The DB connection comes from the `POSTGRES_*` environment variables, which `modules/db_postgres.py` already honours.

## Host config keys (new)

| Key | Default | Meaning |
|---|---|---|
| `remote_worker.enabled` | `false` | Master switch. |
| `remote_worker.phases.<phase_code>` | `local` | `local`, `remote` or `auto`. `auto` means remote when a capable worker has a heartbeat newer than `2 × lease_ttl_seconds`, otherwise local. |
| `remote_worker.lease_ttl_seconds` | `120` | The lease duration. |
| `remote_worker.max_attempts` | `3` | The reaper fails a claim after this many attempts. |
| `worker_gateway.host` / `.port` | `0.0.0.0` / `7861` | The gateway listener. |
| `xmp_sync.mode` | `inline` | `inline` (today) or `outbox`. Remote work always uses the outbox. |

These are **proposed**. Adding them is part of M1, which also documents them in [CONFIG.md](../../technical/CONFIG.md).

## Versioning

- **Schema:** at startup the worker reads `alembic_version`. If it doesn't equal the revision the image was built against, the worker refuses to run and reports that to `/worker/register`. The host version is upgraded first, then the worker.
- **Code:** `worker_version` goes into `remote_workers`, and `executor_version` into `image_phase_status`, as today. Model versions go into `image_model_scores.model_version`.
- **Capabilities:** the worker advertises the phases and model versions it can serve. The host only enqueues `remote` claims for phases that some live worker advertises; otherwise `auto` falls back to local.

## Worker main loop (pseudo)

```text
register → load config → warm models
loop:
  claims = lease_batch()
  if not claims: sleep(backoff); continue
  for c in claims (grouped by image for cache reuse):
     if cancelled(c): skip
     src = fetch(c.image_id, purpose_for(c.phase))       # cache-aware
     out = compute(c.phase, src)                           # functions from spec 04
     with db.transaction():
         persist(c.phase, c.image_id, out)                 # existing writers
         set_image_phase_status(..., 'done')
         outbox_enqueue(c.image_id, kinds_for(c.phase))
         fence(c)                                          # rowcount==1 else rollback
  heartbeat thread extends leases every ttl/3
```
