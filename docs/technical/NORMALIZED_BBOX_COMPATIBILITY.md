---
type: Technical Reference
title: Normalized bird bbox compatibility contract
description: Default-off compatibility reads, backend SQL view authority, verification and reversible deployment prerequisites.
resource: technical/NORMALIZED_BBOX_COMPATIBILITY.md
tags: [localization, database, gallery, rollout]
timestamp: 2026-10-22T02:48:48Z
okf_version: 0.2
---
# Normalized bird bbox compatibility contract

Status: **local implementation; deployment and flag activation pending**. This
contract supports the compatibility period required by Stage 8; it does not
complete that stage, retire a producer, or remove `images.bird_bbox`.

## Authority and public shape

Image list/detail/UUID/hash responses and visual evidence use
[`overlay_bird_bboxes`](../../modules/localization_legacy.py). Gallery SQL
consumers use the backend-owned `image_bird_bbox_compat` view, introduced by
[`0043`](../../migrations/versions/0043_normalized_bird_bbox_compat_view.py),
following `0042`. Fresh bootstrap defines the same view in
[`review.py`](../../modules/db_schema/review.py); a unit check pins SQL equality.
Both representations retain the existing nullable `bird_bbox` JSON shape.

| Available authority | Compatibility value |
|---|---|
| Active bird selection with a matching region/run and positive source dimensions | The selected region's pixel projection; its run may be noncurrent and its region need not be rank zero |
| Active selection whose region/run/dimensions are unusable | The legacy column; do not substitute an unrelated imported result |
| No active selection, current imported outcome with a non-null legacy payload | Original JSON payload, including negative, error, empty or malformed shapes |
| Unselected native shadow run, absent artifacts, or JSON-null imported payload | The legacy column, including SQL NULL |

The Python reader projects normalized geometry through
`localization_selection.legacy_bbox_payload`. The SQL view reads the selection
ledger's `projected_bird_bbox`, recorded by that same projector at promotion.
The ledger projection must match the selected geometry; deployment verification
must reject disagreement rather than infer which artifact is correct. Regions
and projection records must not be edited independently. The current read-only
cohort audit is evidence for the observed data, not a database constraint
guaranteeing that invariant for every possible future mutation.

The view returns `(image_id, bird_bbox)` for every image. Existing partial unique
indexes on active selections and current runs prevent duplicate image rows.
Revoked selections and other detector keys are excluded. The view performs no
detection, source decode, data backfill, or writes. Source dimensions belong to
the selected run; current image dimensions do not replace them.

## Consumer coverage and switches

Backend `localization.read_normalized_first` defaults to `false`. Flag off leaves
serialized rows unchanged and performs no normalized lookup. Flag on batches
up to 500 distinct image IDs per query. Lookup errors are logged and retain the
supplied legacy values. Visual evidence uses this same authority for its region
box and mask. The renderer field and REST schema remain unchanged.

Gallery has a separate optional setting with the same name, also defaulting to
`false`. It loads configuration at startup and requires a restart after changes.
Seven SQL projections cover image lists, detail, both stack-card UNION branches,
stack image lists, sub-stack image lists, and ungrouped stack image lists. The
shared SQL helper selects the compatibility view only when explicitly enabled.
Both `postgres` and `api` SQL providers execute that expression; API-SQL still
requires the existing backend SQL bridge to be enabled. Direct PostgreSQL mode
requires no running WebUI. Gallery's REST consumers follow the backend switch.

Gallery implementation and operational guidance:
[database design](https://github.com/synthet/image-scoring-gallery/blob/main/docs/architecture/02-database-design.md).
Its example configuration documents the flag; no runtime configuration is changed
by this implementation. Enabling the gallery flag before the view exists causes
a SQL error. It does not silently hide a missing deployment with legacy output.

## Deployment and rollback prerequisites

1. Review and deliver the coordinated backend and gallery changes. Inspect the
   actual database identity, migration head, dependent consumers and application
   roles. Take and verify a fresh local backup before an authorized deployment.
2. Apply revision `0043` only in that authorized deployment, before enabling the
   gallery flag. The migration creates/replaces a view and changes no source
   rows. PostgreSQL still takes catalog/relation locks; test the deployment path
   and set an appropriate lock timeout rather than assume zero lock time.
3. Verify view existence and SELECT permission using each actual application
   role. Compare selected, imported, unselected, NULL, negative and error cases
   against the Python reader. Measure list/detail/stack latency and cardinality
   on representative pages. An isolated fixture is insufficient deployment
   evidence.
4. Resolve the rollout's quality and preservation gates, including the historical
   selection disagreements. Enable each consumer switch only within the
   approved scope; record version, role, cohort, results, errors and timing.
5. Exercise rollback with those same consumers: set each enabled switch to
   `false`, restart the relevant process, and verify legacy outputs and latency.
   This restores legacy reads without inference or data rewrites. Keep the
   additive view installed during application rollback.

Schema downgrade removes only the view, without CASCADE. Disable/restart every
dependent consumer first; externally dependent views can make downgrade fail.
Fresh bootstrap also creates this view, so starting a process that calls
`db.init_db()` from this source tree can change the catalog even with flags off.
Pin/isolate source for separately authorized operational repairs; do not reuse a
previous execution proof that assumed a different schema initializer.

A delivered compatibility release and observed rollback period are still
required before legacy producer retirement. Additional inference attempts,
broad replay, historical value restoration, and physical column removal are
separate decisions; this contract authorizes none of them.

## Decision record

**Proposed for deployment, implemented locally.** Both gallery connectors already
execute PostgreSQL SQL, and the backend owns migrations and the selection
projector. Use an additive backend view to expose the recorded selection
projection to both transports. Jev 1.14 recommended this alternative over shared
state evidence with confidence 0.87; deterministic integrity checks and human
deployment authorization remain separate requirements.

Alternatives considered were TypeScript coordinate projection, which duplicates
rounding and authority rules, and a mandatory REST lookup, which adds a WebUI
dependency to direct PostgreSQL mode and complicates pagination. The view keeps
SQL pagination and renderer payloads stable. Its costs are a coordinated
migration, application-role access checks, query-plan verification, and the
explicit ledger/geometry parity invariant. It still references the legacy column
for fallback; column removal requires a later contract and migration.

## Verification scope

- Python bootstrap/migration parity tests pin revision order and identical SQL.
- Isolated PostgreSQL tests exercise selection/import/shadow authority, invalid
  dimensions and region identity, JSON-null fallback, repeated upgrade,
  downgrade preservation, re-upgrade, and revocation. All fixture/schema work
  rolls back in the test database. These are not a full migration-chain rehearsal.
- Gallery connector-mocked regressions cover all seven projections with both
  providers, enabled/disabled settings and absent-setting defaults. Neighboring
  list/detail/stack/config tests and both TypeScript projects are checked.
- Read-only live-cohort comparisons can evaluate the view body as a CTE without
  creating a production view. They do not prove production role permissions,
  actual HTTP transport, renderer interactions, or observed activation rollback.

See [database schema](DB_SCHEMA.md), [API contract](API_CONTRACT.md), and
[localization rollout](../architecture/pipeline/localization-rollout.md) for
the broader rollout gates. Release notes must distinguish committed fixes from
this uncommitted compatibility work.

