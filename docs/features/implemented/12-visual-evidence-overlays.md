---
type: Implemented Feature
title: Visual evidence overlays (API slice)
description: On-demand evidence payload, focus/noise grids, mask RLE, and GET /api/images/{id}/evidence for gallery inspector layers.
resource: docs/features/implemented/12-visual-evidence-overlays.md
tags: [features, evidence, overlays, api, clean-room]
timestamp: 2026-09-30T00:00:00Z
okf_version: 0.1
---

# Visual evidence overlays (API slice)

**Purpose:** Let clients fetch **precomputed or on-demand** spatial evidence (grids, mask, bands, gates) for inspector overlays without running models in the gallery.

**User-visible behavior (downstream):** Driftara viewer toggles region, mask, keypoints, sharpness map, and noise map; legend and breakdown rows use this API.

**Primary code paths:** `modules/visual_evidence/` (`schema.py`, `grids.py`, `rle.py`, `service.py`); `GET /api/images/{image_id}/evidence` in `modules/api/routers/data_query.py`.

**Contract authority:** [technical/VISUAL_EVIDENCE_API.md](../../technical/VISUAL_EVIDENCE_API.md)

**Not yet shipped:** Persisted sidecars at score time, full Stage 6 invalidation, model mask/keypoint population — see [planned/visual-evidence-stage6-persistence.md](../planned/visual-evidence-stage6-persistence.md).

**Related:** [planning/subject-aware-culling-evidence.md](../../planning/subject-aware-culling-evidence.md) · Hub behaviour [image-scoring clean-room 05](https://github.com/synthet/image-scoring/blob/main/docs/clean-room/05-diagnostics-and-visual-inspection.md)
