---
type: Planned Feature
title: Visual evidence — Stage 6 persistence and invalidation
description: Persist evidence artifacts at inference time, version with rendition hash, and invalidate on detector or rendition changes (#423, #426).
resource: docs/features/planned/visual-evidence-stage6-persistence.md
tags: [features, planned, evidence, localization, clean-room]
timestamp: 2026-09-30T00:00:00Z
okf_version: 0.1
---

# Visual evidence — Stage 6 persistence

**Provenance:** derived from competitive analysis of a commercial application's observable behaviour; contains no code, identifiers, fitted constants or model artefacts from it.

## Goal

Move from **on-demand thumbnail grids** to **cached sidecars** written during localization/scoring, keyed by region id + rendition hash + extractor version.

## Requirements

1. **Write path:** After inference rendition is fixed (#406), run extractors once per primary region; store JSON or DB row linked to `image_id` and region id.
2. **Read path:** `GET /evidence` serves stored artifact; on-demand path remains fallback for dev/fixtures.
3. **Invalidation:** New detector version (#408), new mask provider (#426), or new rendition hash drops stale rows without full library rescan (crop-local recompute).
4. **Burst hooks:** Optional `burst` object for best frame / nearly tied (#424) for explainability §1.

## Acceptance

- Golden grids on synthetic renditions in CI (orientation 1–8).
- Gallery vitest consumes `tests/fixtures/evidence/*.json` unchanged across persistence rollout.
- Leakage grep clean on all clean-room commits.

## Authority

- API shape: [technical/VISUAL_EVIDENCE_API.md](../../technical/VISUAL_EVIDENCE_API.md)
- Rollout context: [architecture/pipeline/localization-rollout.md](../../architecture/pipeline/localization-rollout.md)
- Model inputs: [image-scoring-model visual-evidence-providers-spec](https://github.com/synthet/image-scoring-model/blob/master/docs/features/visual-evidence-providers-spec.md)
