---
type: Technical Reference
title: Localization authority lifecycle
description: Localization authority lifecycle
resource: technical/LOCALIZATION_AUTHORITY.md
tags: [localization, postgres, authority]
timestamp: 2026-10-29T23:47:32Z
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

Before production: verified backup/restore evidence, real scoped qualification,
shadow observation, coordinated gallery deployment, independent switch rollout,
and an activation/rollback receipt. No production action is implied by a merged PR.

