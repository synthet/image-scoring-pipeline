---
type: Plan
title: Visual evidence API and grid ownership
description: REST contract, extractor versioning, and module ownership for focus/noise grids and mask RLE.
resource: docs/planning/visual-evidence-api-and-grids.md
tags: [planning, evidence, api, grids, clean-room]
timestamp: 2026-09-30T00:00:00Z
okf_version: 0.2
status: in_progress
---

# Visual evidence API and grids

> **Canonical API spec:** [technical/VISUAL_EVIDENCE_API.md](../technical/VISUAL_EVIDENCE_API.md)  
> **Shipped slice:** [features/implemented/12-visual-evidence-overlays.md](../features/implemented/12-visual-evidence-overlays.md)  
> **Stage 6 persistence:** [features/planned/visual-evidence-stage6-persistence.md](../features/planned/visual-evidence-stage6-persistence.md)

**Provenance:** derived from competitive analysis of a commercial application's observable behaviour;
contains no code, identifiers, fitted constants or model artefacts from it.

## Ownership

| Concern | Owner |
|---------|--------|
| `focus_grid` / `noise_grid` cell math | `modules/visual_evidence/grids.py` |
| Mask RLE encode/decode | `modules/visual_evidence/rle.py` |
| Response schema + versioning | `modules/visual_evidence/schema.py` |
| Image assembly (thumbnail, bbox, fixture fallback) | `modules/visual_evidence/service.py` |
| Keypoint + mask **providers** | image-scoring-model → backend persistence (#426) |

Cell sizes (`16` px focus, `20` px noise, mask `max_dim` `256`) are **starting points** to re-fit.

## API

- `GET /api/images/{image_id}/evidence` — returns `EvidencePayload` JSON.
- Display gates (`gates.*`) and `limitations[]` drive gallery chip enablement.
- Invalidation keys: region id + `rendition_hash` + `extractor_version` (see subject-aware evidence plan §4).

## Tests

- `tests/fixtures/evidence/synthetic_orientation_1.json` — golden payload for gallery vitest.
- `tests/test_visual_evidence.py` — grid shape, RLE roundtrip, fixture validation.

## Non-goals

- Reference product colours or UI strings in API responses.
- Client-side ONNX in gallery for evidence layers.
