---
type: Feature Spec
title: "Spec 01: decode-once rendition"
description: One orientation-baked decode per image produces the thumbnail and a cached ~2048 px inference rendition that later phases reuse instead of re-decoding the source.
resource: docs/specs/pipeline-streamlining/01-rendition.md
tags: [specs, pipeline, rendition, thumbnails, raw, performance]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
status: proposed
---

# Spec 01: decode-once rendition

**Issue:** #406 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M1

## Summary

Today each phase decodes the source file itself:
- **Thumbnails** (`metadata`): `thumbnails.generate_thumbnail`.
- **Localization:** `localization.decode_for_localization`.
- **Scoring:** `MultiModelMUSIQ.convert_raw_to_jpeg`, which writes a temp JPEG per image.
- **BioCLIP and other ML consumers:** `thumbnails.open_rendition_for_ml`.

A RAW decode costs 0.5–0.7 s (#387 smoke test), several times the cost of a detector pass. RAW
thumbnails are also not orientation-baked: `generate_thumbnail` copies the EXIF `Orientation` tag
onto the thumbnail instead of rotating the pixels.

This spec adds one **inference rendition** per source image. It is decoded once through the route
localization already uses, with orientation baked, described by a `RenditionDescriptor` and cached
on disk. The thumbnail is derived from it. Consumers migrate to it one at a time, and scoring
migrates only behind a parity gate.

## Users / stakeholders

- **Operator:** faster ingest, and correctly oriented thumbnails.
- **Downstream phases:** localization, species, scoring and keywords share the same pixels, so
  their regions and crops line up.
- **Gallery:** displays thumbnails. Baked thumbnails change how orientation must be handled
  (see [Assumptions](#assumptions-and-dependencies)).

## Product scenario

A new folder is ingested, and each RAW file is decoded once. Every later phase reads the cached
inference rendition, or regenerates it deterministically if the cache evicted it. A portrait NEF
shows upright in every thumbnail, and a detector box found on the rendition is valid for every
consumer that reads the same rendition.

## Non-goals

- Changing the pixels BioCLIP sees before rollout stage 5. #387 decision 3 kept
  `open_rendition_for_ml` unchanged for that reason.
- Changing scoring's pixels without a parity gate. Percentile anchors are calibrated on the current
  conversion.
- Keying thumbnails by content. They stay keyed by path hash (`get_thumb_path`) for compatibility.
- Import-time hashing and EXIF enrichment, which is covered by
  [import-phase-enrichment.md](../../planning/import-phase-enrichment.md).

## User stories

- As an operator, I want each RAW file decoded once, so that a folder ingests faster.
- As a reviewer, I want portrait RAW thumbnails upright without relying on a copied EXIF tag.
- As a pipeline developer, I want one function that returns the inference pixels and their
  identity, so that regions and crops agree across phases.

## Acceptance criteria

- **AC-1** — When a consumer requests the inference rendition for a source, the system shall return
  an orientation-baked RGB image together with its `RenditionDescriptor`.
- **AC-2** — The rendition decoder shall try routes in this order: `JpgFromRaw` with a long edge of
  at least `MIN_EMBEDDED_LONG_EDGE` (2048), then `PreviewImage`, then `rawpy` with `user_flip=0`
  plus EXIF orientation, then ImageMagick.
- **AC-3** — The rendition decoder shall produce the same descriptor hash as
  `localization.decode_for_localization` for the same source bytes.
- **AC-4** — Where `rendition.enabled` is true, the system shall cache each rendition as a JPEG
  under `thumbnails/renditions/{key[:2]}/{key}.jpg`, keyed by the descriptor hash.
- **AC-5** — If a cached rendition is missing, then the system shall regenerate it byte-identically
  from the source.
- **AC-6** — While the rendition cache exceeds `rendition.cache_max_gb`, the pruner shall delete
  the oldest-accessed renditions first.
- **AC-7** — When `metadata` generates a thumbnail while `rendition.enabled` is true, the system
  shall derive it from the inference rendition by downscaling to 512 px.
- **AC-8** — The system shall write rendition-derived thumbnails with orientation baked into the
  pixels and no EXIF `Orientation` tag other than 1.
- **AC-9** — For EXIF orientations 1–8 on RAW and JPEG fixtures, the rendition-derived thumbnail
  shall show the same visual orientation as the display-oriented source.
- **AC-10** — The system shall record a `thumbnail_version` for every thumbnail it writes, so that
  baked and legacy thumbnails can be told apart.
- **AC-11** — Where `rendition.scoring_source` is true, the scoring prep step shall read the
  inference rendition instead of calling `convert_raw_to_jpeg`.
- **AC-12** — The system shall not enable `rendition.scoring_source` by default until a parity run
  on ≥ 200 images shows Spearman ρ ≥ 0.999 per model and a normalized composite |Δ| ≤ 0.005.
- **AC-13** — When a folder is processed with `rendition.enabled` true, the job report shall
  include per-image decode time with p50 and p95 by decode route.

## Assumptions and dependencies

- `modules/rendition.py` (`RenditionDescriptor`, `DecodeRoute`, `build_rendition_descriptor`) and
  `modules/crop_cache.py` (atomic writes, per-key locks, `prune_crop_cache`) are reused, not
  rewritten.
- `localization.decode_for_localization` is the reference decoder: it already applies orientation
  on every route and separates `raw_jpgfromraw` from `raw_preview`.
- **Gallery:** it must not apply EXIF orientation to a baked thumbnail. AC-8 drops the tag, which
  makes that safe, but the gallery team confirms before `rendition.enabled` is turned on. This is
  a cross-repo notice, not an API change.
- **Disk:** a 2048 px JPEG at quality 90 is roughly 0.5–1 MB. The cache is bounded (AC-6) because
  renditions can be regenerated (AC-5).

## Open questions

Recommendations and deadlines: [07 — decision register](07-blockers-and-decisions.md#3-decision-register) (R-1 to R-3).

1. Should legacy unbaked thumbnails be regenerated in bulk? The proposal is lazily only, on the
   next `metadata` run.
2. What is the rendition JPEG quality: 90, or lossless PNG for inference fidelity? The proposal is
   90, measured under AC-12.
3. Should non-RAW JPEG sources also be cached, or read directly?

## Implementation plan

**Goal:** AC-1 to AC-13 pass. Localization and thumbnails use the shared rendition, and scoring
stays on its old path until AC-12.

**Files:**
- `modules/rendition.py`: add `get_inference_rendition(source_path) -> (Image, RenditionDescriptor)`.
- `modules/localization.py`: move `decode_for_localization` behind the new function (AC-3).
- New `modules/rendition_cache.py`, modelled on `crop_cache.py`.
- `modules/thumbnails.py`: `generate_thumbnail` gains a rendition path gated by `rendition.enabled`.
- `modules/pipeline.py`: the scoring prep gate (AC-11).
- DB: a migration adds `images.thumbnail_version`.

**Approach:**
1. Extract the decoder into `rendition.py` unchanged, and point `localization.py` at it. This is a
   pure refactor, and its tests assert byte identity.
2. Add the cache and pruner.
3. Switch thumbnail generation behind the flag.
4. Add the scoring prep behind its flag, plus a parity script `scripts/research/rendition_parity.py`.
5. Add decode timing to `BatchMetrics`.

**Tests to write first:**
- `tests/test_rendition_decoder.py`: route order (AC-2) and descriptor parity with localization (AC-3).
- `tests/test_rendition_cache.py`: path layout (AC-4), byte-identical regeneration (AC-5), pruning (AC-6).
- `tests/test_thumbnail_orientation.py`: EXIF 1–8 fixtures (AC-8, AC-9) and version stamping (AC-10).
- `tests/test_scoring_prep_source.py`: flag routing (AC-11).

**Rollback:** set `rendition.enabled=false` and `rendition.scoring_source=false`. The cache can be
deleted safely. `thumbnail_version` stays, and legacy thumbnails remain valid.
