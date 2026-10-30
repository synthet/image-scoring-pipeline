---
type: Technical Reference
title: Localization authority lifecycle
description: Localization authority lifecycle
resource: technical/LOCALIZATION_AUTHORITY.md
tags: [localization, postgres, authority]
timestamp: 2026-10-30T07:00:00Z
okf_version: 0.2
---
# Localization authority lifecycle

The runtime is dormant by default. Migration 0046 adds scoped approvals and an
independent `localization.selection_freshness.enabled` control persisted as
`localization_authority_control.selection_freshness_enabled`, default false.
Installing code or schema grants no policy approval and enables no processing.

## Modes and readers

`off` stops new applications and preserves valid selections. `shadow` records
evaluations/proposals without production writes. `active` permits fenced,
qualified applications after explicit activation. Explicit revocation invalidates
managed geometry immediately; bounded cleanup restores only policy-owned projections.
The CPU worker also processes invalid managed selections while off, but shadow
never performs cleanup. Turning authority off does not turn freshness off.

Freshness protection takes precedence over normalized-reader preferences. Scalar,
batch, API, species-input and compatibility-view readers exclude revoked policies,
source/version changes and rendition changes. Source-path changes invalidate the
observation transactionally. A valid selection may name a non-current artifact.
Stale projected boxes cannot return through legacy fallback. Curated historical
selections without managed lineage retain explicit legacy compatibility.

Gallery PRs must apply the persisted backend switch for both direct PostgreSQL
and API-SQL consumers, including list/detail and stack-card queries. Older schemas
keep their original reader behavior until migration 0046 is installed.

## Qualification and publication

The frozen R2 rule/hash and original population remain unchanged. Runtime
population/replacement policies have a separate immutable identity and exact
detector/config/rendition scope. Reservations apply by image ID across repairs;
no automatic release exists. Missing inventory blocks application.

Qualification uses `localization-qualification/1` with exact policy hash, rule
hash, scope, `source_kind=real_holdout`, `synthetic=false`, `geometry_bands` and
separately declared `species_allowed`/`species_bands`. Species bands can include
only qualified medium/large bands. The receipt SHA is supplied independently.

`source_receipts` maps relative filenames to SHA-256 hashes. The named
`validation_manifest` binds scope, rule, frame image/run/region/rendition identities,
bands and calibration control answers. Each judge names a hashed `raw_file`
(`localization-judge-receipt/1`) containing its name, controls and per-image votes.
Declared results must equal those receipts. Normalize provider replies offline
while retaining original evidence; this parser never calls providers or creates
labels. At least three distinct judges must each parse 19/20 controls and score
18/20. Qualified bands require 130 validation images and a Wilson 95% lower bound
of 0.90 on resolved usable labels. R2 additionally verifies its pinned original
freeze/sample/owner answer-key artifacts. See the unchanged
[promotion gate](../reports/localization-promotion-gate-2026-10-26.md).

These files support an explicit identified operator decision; engineering tests
are not qualification evidence. Synthetic approvals exist only as isolated SQL
test fixtures and have no production override flag.

Publication lock order is control, policy/approval, image, then observation/work
and lineage. Claims use 60-second leases renewed every 20 seconds. Publication
rechecks current revisions, artifact/source, original R2 population, ownership,
reservations and lease; late expiry rolls back the entire publication. Replacement
revokes and selects in one transaction. Same-value external assignments are
journaled and preserved. The journal intentionally has no image foreign key,
avoiding lock inversion with resource writers.

## Operator commands and rollback

Use `python -m scripts.maintenance.localization_authority` in the established
backend environment. Every mutation requires `--expect-database` matching the
connected target. Inspect `status` first. The commands are:

1. `register-policy` with the frozen rule and exact producer scope, or
   `register-runtime-policy` with a new scope; neither approves anything.
2. `import-reservations --root <verified-frozen-root>`.
3. `approve-policy --policy-hash <hash> --receipt <path> --receipt-sha256 <sha> --actor <name> --confirm`.
4. `set-freshness on --confirm`, followed by
   `activate --policy-hash <hash> --receipt-sha256 <sha> --confirm`.
5. To stop new applications: `set-mode off`. To invalidate an approval:
   `revoke-policy --policy-hash <hash> --reason <reason>`; inspect status and run
   bounded `cleanup-invalid` until drained. External edits are never restored over.

Disabling freshness requires applications already off and a separately reviewed
reader rollback; it may expose legacy stored values. Database downgrade is refused
until a preservation migration is reviewed. Reverting code is not data rollback.

## Species convergence, idle lane and recovery

Migration 0047 makes species scope one predicate (`localization_species_in_scope`):
independent discovery evidence, or a fresh species-qualified selection. Existing
`birds` tags are a legacy baseline; generated compatibility tags never sustain
selection-only eligibility. Species work is keyed by selection, source, approval,
discovery and ownership revisions, and publishes keywords, BioCLIP embedding,
lineage and phase completion in one transaction under the image lock. Only outputs
with verified producer lineage are replaced or removed; curated, ambiguous-origin
and same-value user edits keep user ownership. `localization_visible_image_keywords`
and `localization_visible_image_embeddings*` hide stale generated outputs while
freshness is on; gallery readers use the same views when they exist.

Work runs only in `active` mode. The authority worker performs CPU actions
(`cleanup`, `preserve`, `out_of_scope`) regardless of GPU activity. GPU actions
(`classify`, `fallback`) are admitted only by the repair lane's idle slot, as one
`bird_species` job after detection candidates and only while no pipeline job is
queued or running. Every species item keeps three attempts with 60/300-second backoff.

Targeted negative recovery (migration 0048) re-detects a discovery-positive current
`no_detection` run once per detector-config/source/active-policy identity,
recorded in `localization_recovery_attempts`; a repeat negative ends it. A detector
outage holds the lane 60 s, then 300 s after each later outage job, never until
restart; while the streak lasts each lane job is a one-image canary, and the first
clean canary resumes full batches. Outages consume no per-image attempts.

Read during activation and rollback:

- `GET /api/runs/drive/status` → `localization_lane`: `hold_reason`,
  `hold_seconds_remaining`, `outage_streak`, `canary_pending`, `last_job_kind`
  (`restart_required` is always false).
- `localization_authority.species` in the same response (and `status` in the
  maintenance CLI): `refresh_pending`, `cleanup_pending`, `preserved`, `exhausted`,
  `recovery_scheduled`.

Rollback: `set-mode off` stops new species claims and recovery scheduling; completed
outputs stay as published. To withdraw region-derived species, `revoke-policy`: the
images leave scope, readers hide stale generated outputs at once, and the worker's
`out_of_scope`/`cleanup` work removes only lineage-owned outputs (drain until
`cleanup_pending` is 0). Downgrading 0048 only drops the recovery markers; 0047 is
refused until a preservation migration is reviewed.

Before production: verified backup/restore evidence, real scoped qualification,
shadow observation, coordinated gallery deployment, independent switch rollout,
and an activation/rollback receipt. No production action is implied by a merged PR.

