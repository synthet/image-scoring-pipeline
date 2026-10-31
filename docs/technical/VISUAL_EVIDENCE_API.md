---
type: Technical Reference
title: Visual evidence REST API and diagnostics
description: On-demand display-raster diagnostics, immutable artifacts, provenance and v1 compatibility.
resource: docs/technical/VISUAL_EVIDENCE_API.md
tags: [technical, api, evidence, overlays]
timestamp: 2026-10-30T16:20:00Z
okf_version: 0.2
status: implemented
---

# Visual evidence REST API and diagnostics

Gallery and the web image inspector share the same backend diagnostics. The four-button row has Bounding Box, Eyes, camera Focus Point and More diagnostics. More contains sharpness, focus peaking, noise, subject mask and eyes/head detail. No inference runs merely from opening a viewer or the menu.

## Version 2 endpoints

| Operation | Contract |
|---|---|
| GET /api/images/{id}/evidence?schema_version=2 | Read cached manifest and capability states; never schedules computation |
| POST /api/images/{id}/evidence/requests | JSON layers (one to five of sharpness, peaking, noise, mask, head) and optional refresh boolean; 202 with manifest and request_id |
| DELETE /api/images/{id}/evidence/requests/{request_id} | Release this subscriber only; 204, or 404 for wrong image or expired request |
| GET /api/images/{id}/evidence/artifacts/{artifact_id} | Image-scoped PNG/JPEG bytes; private immutable cache headers; 404 for invalid, evicted or cross-image identities |

Unknown images return 404. Unsupported layers return 422. Request capacity returns 429; clients may retry. Artifact IDs are opaque content identities, never filesystem paths. No endpoint writes scores, source photographs, localization or keypoint records.

The manifest contains evidence_schema_version: 2, extractor_version, image_id, identity, rendition (nullable until requested) and layers. Each layer has state: not_requested, queued, running, ready, unavailable or failed. Entries may contain reason, artifacts, grid, measurements and provider_version. POST adds request_id. Refresh bypasses cached layer results; existing immutable artifact IDs remain valid until eviction.

## Pixel identity and geometry

A requested job decodes using the existing localization decoder, applies EXIF orientation, saves a display JPEG at quality 95 with no chroma subsampling, then measures those exact saved pixels. Both clients display that preview before drawing diagnostics. Rendition fields include preview_artifact, display_width, display_height, orientation, decode_route, source_hash/version, source_rendition_hash, rendition_hash, source_resolution and pixel_policy. Source paths are excluded.

Source resolution is decoded_native for direct rasters, RAW demosaicing and the JpgFromRaw decode route; raw_preview and raw_magick are marked reduced. This describes the decoded route, not a sensor-resolution guarantee. Focus peaking is unavailable on reduced previews.

Subject/head layers require the selected bird region, while localization selection freshness holds (a newer unselected run is never used; without a fresh selection the layers are unavailable), with matching source identity and display_normalized coordinates, plus exact original rendition hash, orientation, decode route and compatible dimensions. Stale geometry is unavailable with regeneration guidance. Head detail also needs reliable stored landmarks. The backend resolves platform path variants without changing database paths.

## Measurements and display scales

Extractor diagnostics-2.1 uses 64-pixel cells, preserving remainder rows/columns. A grid has cells_x/y, x_edges/y_edges, raw values, values_normalized, units, normalization: fixed_display_scale and display_scale. Null means insufficient evidence; clients leave that cell transparent. Clients never normalize each image independently.

- Sharpness: Laplacian RMS after subtracting the estimated independent-noise contribution (20 times sigma squared). Display scale 0.12. Region/background ratios use verified box cells and are explicitly region measurements.
- Noise: Haar diagonal-band MAD on low-structure samples, rejecting strongly correlated texture. Display scale 0.08 in decoded luma units. It is not a RAW sensor noise measurement.
- Peaking: tiled 512-pixel extraction with 12-pixel halos; blurred-gradient outlines and difference-of-Gaussians texture, separately selectable or combined. Threshold floors 0.012/0.010; noise suppression multipliers 0.85/1.5. These versioned display parameters are covered by synthetic blur/noise tests and are not calibrated quality grades.
- Subject mask: real local segmentation prompted by the verified primary box. Artifacts are foreground mask, background alpha and contour. Only the background is dimmed. Confidence is model mask confidence, independent of image quality.
- Eyes/head: reliable landmarks (confidence at least 0.8) inside the subject region define a head frame and facing vector. Eye patches scale with head size (minimum 16 pixels). Numeric eye/head sharpness ratios carry small-head/low-contrast limitations; no good/bad bands. Existing Eyes markers are reused.

## Scheduling and cache

One CPU worker and one model worker share duplicate jobs through separate subscriber IDs. Cancelling one viewer preserves another subscriber's work. CPU work checks cancellation per row/tile. Model work waits while scoring or other GPU runners are active; a subprocess is terminated if scoring starts or the last subscriber cancels. A model attempt times out after 180 seconds. Shutdown closes both workers.

Derived data lives in thumbnails/evidence-v2 by default, with atomic writes and LRU bundle eviction. Active jobs and artifact responses pin their bundle. Cache keys include image/source identity, geometry, keypoint run, decoder policy, extractor version and model code/weights identity. Request bookkeeping is bounded at 512 subscriptions. Cache data survives restarts; it is disposable and requires no migration.

| Setting | Default |
|---|---|
| EVIDENCE_CACHE_DIR | thumbnails/evidence-v2 |
| EVIDENCE_CACHE_MAX_BYTES | 2147483648 |
| DIAGNOSTICS_ENABLED_LAYERS | sharpness,peaking,noise,mask,head; empty disables all |
| EVIDENCE_MODEL_PYTHON | isolated .agent/tmp/diagnostics-venv interpreter, otherwise current interpreter |
| EVIDENCE_SAM2_CHECKPOINT | models/sam2.1_hiera_tiny.pt |

## Optional local model setup

Install only during explicit provisioning, into a separate environment. The request path never installs packages or downloads weights. The scoring environment is unchanged.

1. Create .agent/tmp/diagnostics-venv with python -m venv --system-site-packages.
2. With its interpreter, install requirements/diagnostics-models.txt using SAM2_BUILD_CUDA=0 and pip --no-build-isolation, then install the sibling image-scoring-model package with --no-deps.
3. Place the official SAM 2.1 Hiera Tiny checkpoint at models/sam2.1_hiera_tiny.pt. Expected SHA256: 7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69.
4. Check provider availability, request a verified image and confirm actual contour output. Missing runtime, weights or geometry remains unavailable.

SAM 2 source is pinned to commit 2b90b9f5ceec907a1c18123530e92e794ad901a4 in the optional requirements. Provider source belongs to image-scoring-model/src/eye_quality/segmentation.py. Backend invokes that file directly in the isolated interpreter, avoiding package initialization that could initialize unrelated models.

Local validation on 2026-10-30: all five layers completed for image 71662 at 8256 by 5504 in approximately 32 seconds including cold model startup. Mask coverage was 17.1%, predicted mask confidence 0.950, eye/head ratio 1.25. This is an integration smoke test, not corpus calibration.

## Version 1 compatibility

GET without schema_version keeps EvidencePayload version 1 and its existing field names. It returns real thumbnail grids when available. Missing pixels return disabled gates and source_unavailable. Production no longer loads demonstration evidence, fabricates a rectangular segmentation mask or returns placeholder criterion grades. Unmeasured subject separation stays null. Background-first RLE accepts a leading zero run and validates exact raster coverage.

Gallery usage is documented in the [viewer feature](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/09-visual-evidence-overlays.md). API routing lives in modules/visual_evidence/http.py; shared computation and cache live beside it.
