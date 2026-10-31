---
type: Report
title: Session digest — localization rollout gap analysis and autofocus focus evidence (2026-10)
description: Consolidated record of October 22–23, 2026 sessions performing gap analysis on the localization rollout summary, investigating the 11-frame autofocus (AF) focus evidence study, and coordinating gallery API contract alignment.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-localization-gaps-and-focus-evidence.md
tags: [session, digest, localization, gap-analysis, autofocus, af-evidence, culling, openapi, transcript]
timestamp: 2026-10-23T00:00:00Z
okf_version: 0.2
status: active
---

# Session digest — localization rollout gap analysis and autofocus focus evidence (2026-10)

**Sources:**
- `2026-10-22-191533-read-docs-reports-localization-rollout-summary-202.md` (38,391 bytes, SHA-256 `66a7ccbbc48679aef2bb364375c8dbc4ea08c470501a396256d4a1d77266f548`)
- `2026-10-22-211837-command-messageresume-taskcommand-message.txt` (131,431 bytes, SHA-256 `b276f587c4f98201d413e2d97d7554acc78b5bf4825e9f8762266bf8dadf2feb`)
- `2026-10-23-201917-command-messageresume-taskcommand-message.txt` (169,854 bytes, SHA-256 `5800a29e2be57836e0002cf35ac72fada5e3d0ce8050631c1cd1648fabe6c914`)
- `codex-session-01a16bd8-30fd-77b0-801c-8cf442b0a2e2.md` (529,960 bytes, SHA-256 `3ef4e51f4d2946b752ab75c945d168e0eeb82de7fe7457e1961d6235e1822622`)

**Classification:** Shareable project knowledge. Scrubbed operator paths and session IDs. No credentials present.

**Related living docs:**
- [docs/reports/localization-rollout-summary-2026-10-22.md](localization-rollout-summary-2026-10-22.md) — 8-stage rollout summary
- [docs/technical/API_CONTRACT.md](../technical/API_CONTRACT.md) — REST API specifications
- [docs/reference/api/openapi.yaml](../reference/api/openapi.yaml) — OpenAPI schema definition

---

## Gap analysis of localization rollout

Review of the master project summary (`localization-rollout-summary-2026-10-22.md`) against production reality identified several divergence points requiring synchronization before Phase 2:

1. **Selection ledger vs consumer view:** While the selection ledger (`image_localization_selections`) holds 4,675 active records (4,401 large/medium and 274 small), the gallery frontend and legacy backend tools still relied primarily on the legacy `images.bird_bbox` column.
2. **Phase 2 scope boundaries:** Epic #345 was closed, but issue #407 (Stage 4 slice 2) remained open with outstanding work items:
   - Synchronizing `ImageEyeKeypoints` between the backend models and gallery TypeScript types.
   - Enforcing strict region boundaries in visual culling views.
3. **OpenAPI contract drift:** New query parameters for region filtering were implemented in code but lacked formal representation in `openapi.yaml`.

---

## The 11-frame autofocus (AF) focus evidence study

Worktree `docs/af-focus-evidence` (evaluated in Codex session `01a16bd8`) analyzed an 11-frame sequence of raptor flight bursts (Kestrel dataset) to investigate whether camera autofocus metadata can be leveraged as an independent ground-truth signal for image scoring and burst culling.

### Findings on autofocus metadata

1. **Coordinate normalization hurdles:**
   - Camera EXIF tags (specifically Nikon `AFPoints` and Sony MakerNotes) record focus points in native sensor coordinates, unscaled by digital crop or aspect ratio.
   - Accurately determining whether an AF point falls inside a bird's bounding box requires parsing camera model, sensor active area, orientation rotation, and uncropped dimensions.
2. **Discriminative power for culling:**
   - In 9 out of 11 frames, the active locked AF point directly intersected the detected bird bounding box.
   - Frames where the AF point missed the bird box (locking onto background foliage) correlated strongly with lower sharpness metrics, confirming that AF-box intersection is a high-signal candidate for rapid pre-culling in burst sequences.
3. **Limitations identified:**
   - AF point metadata is absent or unparseable in approximately 22% of legacy or non-RAW formats.
   - Relying on AF metadata must remain strictly an additive signal rather than a gating requirement.

---

## Technical outcomes & decisions

- **Contract synchronization:** Verified that the REST API and `openapi.yaml` accurately document `/api/images/{id}/regions` and normalized box schemas.
- **Isolation of WIP branches:** The focus evidence study was cleanly isolated to `docs/af-focus-evidence` without polluting the core codebase, while issue #407 tracking was updated with precise acceptance criteria.
- **Rollout documentation update:** `docs/reports/localization-rollout-summary-2026-10-22.md` was finalized and committed as the canonical one-page reference for the rollout state.
