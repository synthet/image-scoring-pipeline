---
type: Technical Spec
title: Visual evidence REST API and payload
description: Canonical JSON contract for GET /api/images/{id}/evidence consumed by the gallery and operator tools.
resource: docs/technical/VISUAL_EVIDENCE_API.md
tags: [technical, api, evidence, overlays, clean-room]
timestamp: 2026-09-30T00:00:00Z
okf_version: 0.1
status: partial
---

# Visual evidence API

**Provenance:** derived from competitive analysis of a commercial application's observable behaviour; contains no code, identifiers, fitted constants or model artefacts from it.

## Endpoint

```
GET /api/images/{image_id}/evidence
```

- **404** when `image_id` is unknown.
- **200** body: `EvidencePayload` (see below).
- Coordinates and grids are in **display-oriented** space (same convention as `bird_bbox` and eye keypoints).

Implementation: `modules/visual_evidence/` · Router: `modules/api/routers/data_query.py`.

## Versioning

| Field | Meaning |
|-------|---------|
| `evidence_schema_version` | Integer; bump when response shape or field semantics change. Current: **1**. |
| `extractor_version` | String; bump when grid math, noise estimator, or mask downsample changes. Current: **`visual_evidence_extractors_v1`**. |
| `rendition_hash` | Short hash of thumbnail path + raster size; invalidation with region id (see Stage 6 plan). |

## Top-level object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image_id` | int | yes | Database id |
| `display_width` | int | yes | Width of evidence raster (thumbnail greyscale used today) |
| `display_height` | int | yes | Height of evidence raster |
| `gates` | object | yes | Which overlay toggles the client may enable |
| `limitations` | string[] | no | Why layers are disabled (`no_region`, `mask_low_confidence`, `keypoints_heuristic`, `small_subject_second_pass`) |
| `criteria` | array | no | Criterion bands for explainability rows |
| `focus_grid` | grid | no | Sharpness cells |
| `noise_grid` | grid | no | Noise cells |
| `mask_rle` | object | no | Downsampled binary mask, run-length encoded |
| `separation` | object | no | Subject/background sharpness ratio and noise summary |
| `region_bbox` | object | no | Primary subject box (same fields as `bird_bbox` when present) |
| `keypoints` | array | no | Reserved for model provider output |
| `burst` | object | no | Reserved for best frame / nearly tied (#424) |

### `gates`

| Key | When true |
|-----|-----------|
| `region` | Subject box may be drawn |
| `mask` | Mask overlay allowed |
| `keypoints` | Keypoint overlay allowed |
| `focus_grid` | Sharpness heatmap allowed |
| `noise_grid` | Noise heatmap allowed |

### Grid object

| Field | Type | Notes |
|-------|------|-------|
| `cells_x` | int | Column count |
| `cells_y` | int | Row count |
| `cell_size_px` | int | **Starting point** to re-fit (focus default 16, noise default 20) |
| `values` | float[] | Row-major raw cell metrics |
| `values_normalized` | float[] | Optional 0–1 per cell for client colour mapping |

### `mask_rle`

| Field | Type | Notes |
|-------|------|-------|
| `width`, `height` | int | Mask dimensions (may be downsampled) |
| `counts` | int[] | Alternating run lengths, C order, starting with background |
| `max_dim` | int | Downsample cap **starting point** 256 |

### `separation`

| Field | Type | Notes |
|-------|------|-------|
| `subject_sharpness_mean` | float? | Mean focus metric over subject cells |
| `background_sharpness_mean` | float? | Optional background reference |
| `ratio` | float? | Subject/background sharpness ratio for legend copy |
| `noise_sigma_mean` | float? | Regional noise estimate for legend |
| `mask_label` | string | Human-readable mask scope (default `subject_mask`) |

### `criteria[]`

| Field | Type | Notes |
|-------|------|-------|
| `criterion` | enum | `focus`, `eye`, `exposure`, `composition`, `noise`, `context` |
| `band` | string | Backend-owned code (gallery maps via design package) |
| `sub_score` | int? | 0–100 display sub-score |
| `confidence_evidence` | float? | 0–1 evidence confidence (not decision confidence) |

## Assembly behaviour (current slice)

1. Load `thumbnail_path` and `bird_bbox` for the image.
2. If thumbnail unreadable, return fixture `tests/fixtures/evidence/synthetic_orientation_1.json` when present, else minimal payload with `limitations: ["no_region"]`.
3. Compute focus and noise grids on greyscale; optional bbox mask weights cells.
4. Encode bbox mask to RLE when a region exists.

Full pipeline persistence and invalidation: [visual-evidence-stage6-persistence.md](../features/planned/visual-evidence-stage6-persistence.md).

## Fixtures & tests

- `tests/fixtures/evidence/synthetic_orientation_1.json`
- `tests/test_visual_evidence.py`

## Consumers

- Gallery: [09-visual-evidence-overlays.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/09-visual-evidence-overlays.md)
- UI tokens: [evidence-overlays-design-spec.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/features/evidence-overlays-design-spec.md)
