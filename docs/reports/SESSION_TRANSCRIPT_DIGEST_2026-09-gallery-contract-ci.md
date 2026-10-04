---
type: Report
title: Session digest — gallery contract gate and ESLint (#164 / #177)
description: Cross-repo facts from September 2026 sessions on making gallery ESLint blocking, syncing OpenAPI snapshots with backend analytics routes, and fixing electron.d.ts type-sync after merging eye-keypoint UI.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-09-gallery-contract-ci.md
tags: [session, digest, gallery, ci, openapi, eslint, cross-repo]
timestamp: 2026-09-27T16:55:00Z
okf_version: 0.2
---

# Session digest — gallery contract gate ([#164](https://github.com/synthet/image-scoring-gallery/issues/164) / [#177](https://github.com/synthet/image-scoring-gallery/pull/177))

Distilled from **image-scoring-gallery** delivery work; backend OpenAPI is schema authority.

## ESLint gate (#164)

- Gallery CI **removed baseline-forgiving ESLint** once repo errors were cleared; lint is **blocking**
  on the `Test and Contract Gate` workflow.
- Scope included splitting bird-bbox styling helpers, calendar picker tests, and App mode context
  refactors without reintroducing `no-explicit-any` debt.

## OpenAPI / contract drift

- Backend **master** added `/api/analytics/scores/*` routes and schemas; gallery keeps a **pinned
  OpenAPI snapshot** for drift detection.
- PRs that only touch gallery still fail the contract job when the snapshot lags backend — refresh the
  snapshot from canonical backend `openapi.yaml` / export artifact, not hand-edited paths.

## Type-sync failure after merging `main` (#177)

| Check | Failure |
|-------|---------|
| `npm run check:type-sync` | `ImageEyeKeypoints` present in `import type { … }` from `electron/types.ts` but missing from the matching `export type { … }` block in `src/electron.d.ts` |

**Fix:** add `ImageEyeKeypoints` to the re-export list so import and export sets match (see
`scripts/check-type-sync.mjs`).

Eye-keypoint overlay UI (`getEyeKeypoints` IPC, overlay components) landed on `main` concurrently with
the ESLint branch; merge resolution kept overlay code **and** the stricter lint/type gates.

## Related (backend)

- [AGENT_COORDINATION.md](../technical/AGENT_COORDINATION.md) — cross-repo API workflow
- [API_CONTRACT.md](../technical/API_CONTRACT.md) — REST authority
