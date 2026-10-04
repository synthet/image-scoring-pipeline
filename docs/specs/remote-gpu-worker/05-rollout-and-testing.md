---
type: Feature Spec
title: "Remote GPU worker 05: rollout and testing"
description: Milestone breakdown, test matrix, local-vs-remote parity gates, security checklist and operator runbook for the remote GPU worker.
resource: docs/specs/remote-gpu-worker/05-rollout-and-testing.md
tags: [specs, remote-worker, rollout, testing, runbook]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.2
status: proposed
---

# Remote GPU worker 05: rollout and testing

**Epic:** #435 · **Hub:** [INDEX.md](INDEX.md)

## Milestones

| M | Issue | Delivers | Exit criteria |
|---|---|---|---|
| M1 | #437 | Migration `0036_remote_worker`, mirrored in `modules/db_postgres.py`: claim lease columns, `remote_workers`, `xmp_sync_outbox` plus its trigger. Also: `scripts/maintenance/create_worker_role.sql`; the gateway app (auth, register/heartbeat, `/worker/config`, rendition and original endpoints, its own OpenAPI file); the outbox drainer; the config keys, with [CONFIG.md](../../technical/CONFIG.md) updated. | Postgres tests for [03](03-xmp-outbox.md) AC-1–AC-5. Gateway API tests. With `xmp_sync.mode=outbox` locally, sidecars match inline mode on the fixture set. |
| M2 | #438 | `ImageSource`, the compute/persist split and `xmp_sync.emit`, per [04](04-phase-decoupling.md) | [04](04-phase-decoupling.md) AC-1–AC-5. No behaviour change in local mode. |
| M3 | #439 | `modules/remote_worker/`, `Dockerfile.worker`, `docker-compose.worker.yml`, `requirements/requirements_worker_gpu.txt` | Postgres tests for leasing, fencing and the SKIP LOCKED race. The worker starts only when the schema version matches. |
| M4 | #440 | `RemotePhaseExecutor`, the lease reaper, the `auto` mode, cancel propagation, worker status in `/app`, a `diagnostics.*` MCP action | A run with `remote_worker.phases.scoring=remote` completes end to end against a fake worker, in the Postgres API E2E suite. |
| M5 | #441 | Phases enabled one at a time: scoring → keywords → culling embeddings → localization → bird_species | A parity report per phase in `docs/reports/`. A phase is enabled in `auto` only after it passes. |
| M6 | #442 | TLS option, metrics, a two-worker load test, the runbook below completed | The load test holds throughput with no duplicate claims. The runbook is verified on the real LAN setup. |

## Test matrix

The markers match `pytest.ini` and the E2E vocabulary in `AGENTS.md`.

| Layer | Suite | Covers |
|---|---|---|
| Unit (fast subset) | `tests/test_remote_worker_*.py` | Lease SQL builders, backoff, the cache-key and ETag logic, both modes of `xmp_sync.emit`, gateway auth (a fake token store), id-only lookup, the headers for each input mode, config redaction (no `database.*` and no secrets in `/worker/config`) |
| Postgres integration (`-m postgres`) | `tests/integration/test_remote_worker_e2e.py` | Two simulated workers racing on the same claims never share one; an expired lease is requeued, then fails after `max_attempts`; the fence rejects a late commit, leaving no partial rows; cancel stops the item before its commit; outbox coalescing plus NOTIFY-on-commit; the drainer recovers from polling |
| Docker inference E2E (`tests/e2e_docker/`) | `test_remote_parity.py` | The same fixture images run locally and on a worker container, in both input modes, per phase ([Parity gates](#parity-gates)) |
| Contract | `scripts/ci/contract_check.py` | The main API is unchanged. The gateway has its own OpenAPI file and a check of its own. |

## Parity gates

For each phase, compare the local and remote runs of the same images, in each input mode:

| Phase | Compare | Tolerance |
|---|---|---|
| `scoring` | `image_model_scores.raw_score` per model; `images.score_*`, `rating`, `label` | Raw \|Δ\| ≤ 1e-3 when the pixels are identical (`rendered`). `original` mode: report \|Δ\| per decode route. Rating must match. |
| `keywords` | Keyword set, title, description; CLIP and BLIP vectors | Keywords must match exactly; cosine ≥ 0.999 |
| `culling` embeddings | MobileNetV2 1280-d vectors | Cosine ≥ 0.999 |
| `localization` | Region boxes and classes, `decode_route` | IoU ≥ 0.95 per matched box; same class; decode route recorded |
| `bird_species` | Top-1 species keyword, confidence | Same top-1; \|Δconfidence\| ≤ 1e-3 |

The report states the **decode route** for both runs. When the routes differ, which is possible in `original` mode, a mismatch counts as a finding to explain, not an automatic failure (INDEX D-4).

## Security checklist (M1 and M6)

- [ ] The gateway listens on its own port. The webui stays on `127.0.0.1` (`webui.py:163`).
- [ ] Each worker has its own token, stored hashed in `secrets.json`. Revoking one token blocks that worker only.
- [ ] Gateway endpoints accept `image_id` only. There is no path parameter anywhere, and paths are resolved and checked on the host.
- [ ] `/worker/config` never returns `database.*`, tokens or `get_secret` values. A test enforces it.
- [ ] Postgres role `image_scoring_worker`: no DDL and no `TRUNCATE`; `DELETE` only where the keyword-replace path needs it; `pg_hba` allows the worker's IP only.
- [ ] Optional `sslmode=require` and TLS on the gateway (M6).
- [ ] The worker never uses `/api/db/query` or the `X-DB-Write-Token`.

## Operator runbook (draft, completed in M6)

### One-time host setup

1. Upgrade the host and run the migrations up to `0036_remote_worker`.
2. Create the role: `psql -f scripts/maintenance/create_worker_role.sql`, then set its password through the environment.
3. **Postgres networking.**
   - Set `listen_addresses` to include the LAN interface.
   - Add a `pg_hba.conf` line: `host image_scoring image_scoring_worker <worker-ip>/32 scram-sha-256`.
   - In Docker, keep the `5432` port mapping and firewall it to the worker's IP.
4. **Config.** Add `remote_worker.enabled=true` and `worker_gateway.port=7861`, and put a worker token in `secrets.json`.
5. **Start the gateway,** either as the compose service `worker-gateway` or as the second listener, and check `GET /worker/config` using the token.

### Worker machine

1. Install Docker and the NVIDIA container toolkit, and make sure `nvidia-smi` works inside a container.
2. Clone the repo at the **same revision** as the host, then run `docker compose -f docker-compose.worker.yml build`.
3. Create `worker.json`: `gateway_url`, `worker_id`, `input_mode`, `phases`, `cache_dir`, `cache_max_gb`. Set the `POSTGRES_*` variables to point at the host.
4. `docker compose -f docker-compose.worker.yml up -d`. Check that the worker appears as `online` in `/app`.

### Enabling phases

- Set `remote_worker.phases.scoring=auto`, and add the others in the M5 order once each has passed its parity gate.
- `auto` falls back to local when no capable worker has a fresh heartbeat.

### Recovery

| Symptom | Action |
|---|---|
| Claims stuck in `running` | Check the worker's heartbeat. The reaper requeues expired leases on its own; lower `lease_ttl_seconds` if recovery is too slow. |
| Outbox lag is growing | Check that the drainer thread is alive (`/app`), and look at the dead letters' `last_error`. Retry the dead letters per folder. |
| The worker refuses to start with a schema mismatch | Upgrade the worker to the host's revision. Always upgrade the host first. |
| A worker is compromised or retired | Revoke its token, set `remote_workers.status='offline'`, and rotate the worker DB password. |

### Upgrades

1. Drain: set the worker's status to `draining`, and wait for its claims to finish.
2. Upgrade the host and run the migrations.
3. Upgrade the worker to the same revision.
4. Resume.
