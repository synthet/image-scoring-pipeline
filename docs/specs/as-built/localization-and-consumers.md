---
type: Technical Reference
title: Localization and consumer ownership as built
description: Renditions, provider cascade, immutable artifacts, revocable selection, species fallback and repair.
resource: specs/as-built/localization-and-consumers.md
tags: [specification, as-built, localization, persistence]
timestamp: 2026-10-23T00:00:00Z
okf_version: 0.2
---

# Localization and consumer ownership as built

Observed source revision `321d3a15f5ebf5f2de62cc212eb087eccf548f2e`, plus the dated review's frozen working
sources. Canonical overview: [pipeline localization](../../architecture/pipeline/INDEX.md).
Detection artifacts, production selection and downstream consumption are three independent decisions.

## Rendition and provider flow

[decode_for_localization](../../../modules/localization.py) obtains display-oriented RGB and a
[RenditionDescriptor](../../../modules/rendition.py). Descriptor identity hashes source identity/version,
decode route, applied orientation, display dimensions, color policy and descriptor version; source path and
informational notes are excluded. Source identity `size-mtime-head-1` samples size, integer mtime and first
65536bytes; it is **not** a full-file content digest. A same-size/same-mtime tail edit can evade this identity.
RAW embedded preview, rawpy, ImageMagick and direct raster decodes are different routes and may have
different dimensions/color/crop. Coordinates must name the rendition, not just the filename.

[rendition_cache](../../../modules/rendition_cache.py) caches RAW display-oriented JPEGs at long edge2048,
quality90, no upscaling. Cache key includes source identity/version, requested long edge, quality and cache
version1. A miss writes then re-reads JPEG bytes so first and later callers receive the same compressed
pixels. Non-RAW uses direct decode/resize. Corrupt or dimension-inconsistent entries regenerate; per-key
locks and atomic writes coordinate writers; pruning evicts LRU files. Cache infrastructure does not mean all
consumers use it, and this cache does not promise native-resolution eye evidence.

Provider [bird_detection](../../../modules/bird_detection.py) supplies YOLO bird boxes; model-repo defaults
are the source of weight semantics. [RTMDet](../../../modules/detectors/rtmdet.py) is an ONNX animal fallback,
with ONNX digest verified against its manifest. Missing runtime/files disable the provider; hash mismatch
reports weights_mismatch. Input RGB→BGR, centered uniform640 letterbox, pad114, manifest mean/std in float64
then float32 NCHW. Keep COCO animal classes14..23, threshold0.4, NMS IoU.65, maximum10 detections. Optional
0.25 retry is disabled by default; manifest export threshold0.001 is not the application acceptance threshold.

[localization_cascade.combine](../../../modules/localization_cascade.py): detected YOLO boxes win; else
detected COCO animals become animal regions. For COCO area<.02, optional YOLO refinement uses padding1.0
of box size per side, accepts the highest-IoU refined box only at IoU≥.3. Refinement boxes must already be
in frame-normalized coordinates. Provider provenance is yolo:bird, coco:class or coco+refine:class. If neither
provider yields boxes: retryable_error wins; detected/no_detection combinations become no_detection;
otherwise terminal_error precedes disabled. The hash binds both child configs and refine constants.

## Artifacts and production ownership

Localization persists runs/regions/keypoint runs/keypoints with source/rendition identity and status. Region
coordinates are `display_normalized` xyxy; normalized conversion requires positive dimensions and valid
in-frame geometry. Legacy-unverified artifacts cannot acquire verified identity by renaming their space.
“Current localization run” means current artifact, not chosen production answer.

[localization_selection](../../../modules/localization_selection.py) stores the active, revocable choice
separately. `select_region(image_id,region_id,selected_by,evidence,expect_bird_bbox=...)` locks the images row,
checks region image/detector ownership and dimensions, refuses competing active selections, and optionally
compares the existing legacy bbox to the caller's expectation. Successful insertion and projection to
`images.bird_bbox` occur in one transaction. Statuses include selected, missing_image, region_mismatch,
no_dimensions, already_selected, other_selection_active and production_changed. Projection rounds
normalized endpoints×display dimensions to pixel integers, preserves confidence and records frame size/area.

`write_legacy_bird_bbox` locks the **same images row first**, refuses when an active bird selection exists,
and suppresses writes on guard errors. This applies to writes and clears even if region inference is off.
`revoke_selection` restores previous bbox only if the current bbox still equals its projected value;
otherwise revokes ownership but preserves the newer external edit (`revoked_bbox_kept`).
These are compare-and-set contracts, not a license to overwrite newer edits.

## Species and repair consumers

[bird_species.species_input_for_image](../../../modules/bird_species.py) consults **active bird selection**,
never the latest shadow run. `bird_species.use_regions` defaults false. With an eligible selected region,
classify its padded crop; selection lookup errors, no selection or unpadded area<.005 use legacy embedded
detector/full-frame handling. Selected ownership still blocks legacy bbox replacement on fallback. BioCLIP
full-frame and cropped input persist in distinct spaces `bioclip_2_image` and `bioclip_2_crop` (both768D).
Input availability is independent of keyword eligibility and classifier-confidence threshold.

[bird_species_eligibility](../../../modules/bird_species_eligibility.py) derives scope from birds discovery
keywords. A species keyword marks classification; terminal no-species skip state tracks exhaustion;
not-in-scope/pending/exhausted/classified must not be conflated. New keyword writes preserve birds and strip
the legacy birds:species-exhausted marker. Job threshold overrides config min_confidence; crop presence
alone does not force a species label.

[localization_policy](../../../modules/localization_policy.py) records an enablement boundary;
[localization_lane](../../../modules/localization_lane.py) schedules repair only when phase and repair
gates are enabled, for eligible metadata-ready images under its policy. It is a background lane, not a new
hard scoring dependency. Selection promotion, artifact replacement, repair reset and phase summaries are
separate operations; repair must not steal active consumer ownership. Source/rendition mismatch needs a new
artifact and explicit selection decision.

## Acceptance examples

| Trigger | Expected behavior | Evidence |
|---|---|---|
| Promotion holds row lock while legacy writer waits | Writer waits, then refuses after selection commits | [test_bird_bbox_selection_locking](../../../tests/integration/test_bird_bbox_selection_locking.py) |
| Legacy writer commits before promotion expecting null | Promotion returns production_changed | Same isolated PostgreSQL test |
| Selected region exists, region mode disabled or lookup fails | Legacy detector may classify, but cannot overwrite owned bbox | [test_bird_species_selection_ownership](../../../tests/test_bird_species_selection_ownership.py) |
| Same RAW requested twice | Identical cached bytes, no second decode | [test_rendition_cache](../../../tests/test_rendition_cache.py) |
| Missing/stale/failed localization | Consumer fallback and repair rules remain separate | [test_localization_policy](../../../tests/test_localization_policy.py), [test_localization_lane](../../../tests/test_localization_lane.py) |
| Invalid coordinates, EXIF transforms | Reject invalid geometry; preserve coordinate identity | [test_rendition](../../../tests/test_rendition.py), [test_localization_cascade](../../../tests/test_localization_cascade.py) |

Three real PostgreSQL interleaving cases passed in a disposable database with tmpfs storage, no production
mounts, no published ports and no external network; see the hub review receipt. Real-image cascade recall,
small-subject failures, cross-decoder color equivalence and natural-image cache/scoring parity remain field
evaluation gaps. No consumer gate was activated by the review.
