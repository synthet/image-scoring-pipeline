---
type: Feature Spec
title: "Remote GPU worker 03: XMP outbox"
description: A transactional xmp_sync_outbox table with a pg_notify trigger, and a host drainer that writes sidecars from current DB state with coalescing, retries and dead-lettering.
resource: docs/specs/remote-gpu-worker/03-xmp-outbox.md
tags: [specs, remote-worker, xmp, outbox, postgres]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
status: proposed
---

# Remote GPU worker 03: XMP outbox

**Epic:** #435 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M1 (#437)

## Summary

The worker can't reach the sidecars, which live next to the originals on the host. So the worker records **that** an image's XMP-relevant state changed, in the same transaction as the result. A host thread then **re-reads the current state** and writes the sidecar with the existing `modules/xmp.py` writers.

Because the drainer writes current state rather than replaying events:
- duplicate and out-of-order events are harmless;
- the pending rows for one image coalesce into a single write.

## Today

- **Sidecar writes happen inline in the workers.** The call sites are listed in [04](04-phase-decoupling.md#xmp-call-sites).
- **Scores are never written to XMP;** only the derived rating and label are. The keywords path writes keywords, title, description and alt text. Culling writes pick/reject and burst UUID.
- **No outbox, dirty flag or NOTIFY exists.** The only trigger in the schema is the `deleted_images` tombstone (`trg_record_deleted_image`, `modules/db_postgres.py:1199`). The new trigger follows the same style.

## Schema

```sql
CREATE TABLE xmp_sync_outbox (
  id            BIGSERIAL PRIMARY KEY,
  image_id      INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
  kind          VARCHAR(20) NOT NULL,   -- rating_label | keywords | pick_reject | burst_uuid | species
  source        VARCHAR(20) NOT NULL,   -- remote_worker | local (when xmp_sync.mode=outbox)
  worker_id     VARCHAR(64),
  job_id        INTEGER,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  attempts      SMALLINT NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_error    TEXT,
  processed_at  TIMESTAMPTZ,
  dead_at       TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_xmp_outbox_pending ON xmp_sync_outbox(image_id, kind)
  WHERE processed_at IS NULL AND dead_at IS NULL;
CREATE INDEX idx_xmp_outbox_due ON xmp_sync_outbox(next_attempt_at)
  WHERE processed_at IS NULL AND dead_at IS NULL;

CREATE OR REPLACE FUNCTION trg_xmp_outbox_notify_fn() RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('xmp_outbox', NEW.image_id::text);
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_xmp_outbox_notify AFTER INSERT ON xmp_sync_outbox
  FOR EACH ROW EXECUTE PROCEDURE trg_xmp_outbox_notify_fn();
```

- **The producer** inserts with `ON CONFLICT (image_id, kind) WHERE processed_at IS NULL AND dead_at IS NULL DO NOTHING`. A second result for the same image, before the drain, is absorbed by the pending row.
- **NOTIFY is delivered only on commit,** so the drainer never sees an event for an uncommitted result.
- **The worker role** gets `INSERT` on `xmp_sync_outbox`, plus `USAGE` on its sequence, and nothing else on this table.

## Phase → outbox kinds

| Phase | Kinds | What the drainer writes (existing writer) |
|---|---|---|
| `scoring` | `rating_label` | `xmp:Rating`, `xmp:Label`, via `write_metadata_unified` (`modules/xmp.py:631`); embedded too for RAW, as today |
| `keywords` | `keywords` | `dc:subject`, `dc:title`, `dc:description`, alt text, via `write_metadata_unified` |
| `bird_species` | `keywords` (the species land as `species:*` keywords) | Same as `keywords` |
| `culling` (host clustering after remote embeddings) | `pick_reject`, `burst_uuid` | `write_pick_reject_flag` (`:354`), `write_burst_uuid` (`:125`) |
| `localization` | none | Localization writes DB rows only |

## Drainer (host)

A daemon thread starts with the webui when `remote_worker.enabled` is set, or when `xmp_sync.mode=outbox`. It uses its own DB connection.

```text
LISTEN xmp_outbox
loop:
  wait for NOTIFY or poll_interval (default 5 s)
  rows = SELECT … WHERE processed_at IS NULL AND dead_at IS NULL AND next_attempt_at <= now()
         ORDER BY created_at LIMIT batch FOR UPDATE SKIP LOCKED
  group rows by image_id
  for each image:
     state = read current DB state for the pending kinds
             (images.rating/label, keywords + title/description, cull decision, burst_uuid)
     path  = resolve image path on host (modules/paths.py)
     write sidecar via modules/xmp.py for those kinds
     on success: processed_at = now()
     on error:   attempts += 1; last_error; next_attempt_at = now() + backoff(attempts)
                 if attempts >= max: dead_at = now()
```

- **Notifications are wake-ups, not a source of truth.** A missed notification (drainer restart, dropped connection) is covered by the poll.
- **Idempotence.** Writing the same state twice leaves the same sidecar.
- **Ordering.** State is read at drain time, so the sidecar always ends at the latest committed DB state. Intermediate states can be skipped, and that's intended.
- **Concurrency.** `SKIP LOCKED` lets more than one drainer run safely, but one is enough.
- **Backoff:** `min(2^attempts × 5 s, 1 h)`. The default for `max` is 8 attempts.
- **A missing file** (the original was moved or deleted) is dead-lettered straight away, with `last_error='file not found'`.

## Observability

- **Counts:** pending, due, dead-lettered, and the age of the oldest pending row (outbox lag).
- **Where they appear:** the Gradio `/app` status page and the `diagnostics.*` MCP actions.
- **Operator actions:**
  - retry the dead letters for a folder or job;
  - "re-sync XMP for folder", which enqueues `rating_label` and `keywords` for every image in the folder. The same path is useful after restoring a backup.

## Local mode (`xmp_sync.mode`)

- **`inline` (the default).** Local runners keep writing sidecars synchronously, as today. Behaviour doesn't change.
- **`outbox`.** Local runners enqueue too. This is how M1 proves the drainer before any worker exists. Whether to make it the default is INDEX D-2.
- **Remote work always uses the outbox,** whatever this setting says.

## Acceptance criteria

- **AC-1:** Inserting two pending rows for the same `(image_id, kind)` leaves one pending row.
- **AC-2:** A committed insert emits exactly one `NOTIFY xmp_outbox` carrying the `image_id`. A rolled-back insert emits none.
- **AC-3:** The drainer writes the sidecar from the current DB state, and marks the row processed.
- **AC-4:** A writer failure increments `attempts` and sets `next_attempt_at` by backoff. Once `attempts` reaches max, it sets `dead_at`.
- **AC-5:** With the drainer stopped, rows accumulate. When it restarts, polling drains them without any notification.
- **AC-6:** With `xmp_sync.mode=inline`, local runs write no outbox rows, and their sidecar output is unchanged.
