---
type: Report
title: Session digest — bird-detect-v0 integration (2026-07)
description: Non-secret facts extracted from July 2026 agent session exports about integrating synthet/bird-detect-v0 into the bird-species workflow (detect → crop → BioCLIP), complementing the shipped implementation notes in docs/log.md.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-07-bird-detect-v0.md
tags: [session, digest, bird-detection, bird-species, transcript]
timestamp: 2026-09-27T16:55:00Z
okf_version: 0.2
---

# Session digest — bird-detect-v0 integration (2026-07)

Distilled from operator-local session exports (not reproduced here). Public implementation record:
[log.md § 2026-07-26 / 2026-07-27](../log.md), [BIRD_SPECIES_WALKTHROUGH](../technical/BIRD_SPECIES_WALKTHROUGH.md).

## Problem statement

BioCLIP species classification ran on the **full frame**, so small birds were drowned by background. The
requested change was to insert **localization before classification**: detect a bird box, crop in memory,
classify the crop, and persist geometry for later phases.

## Design decisions (confirmed in session)

| Topic | Decision |
|--------|----------|
| Model packaging | Ultralytics YOLO **`.pt`** weights (`synthet/bird-detect-v0` on Hugging Face) |
| No detection | **Fallback to whole image** (still run classification) |
| Multiple boxes | Use **highest-confidence** box after ranking |
| Persistence | Store **bounding box JSON** on the image row (later normalized as `bird_bbox` / localization) |
| Integration point | `BioCLIPClassifier.classify()` — detect → crop → classify |

## Environment constraints noted in session

- Automated fetches to `huggingface.co` from the agent sandbox hit **egress 403**; model details were
  confirmed interactively (YOLO `.pt`) rather than from the model card.
- Existing repo surface already included a full `bird_species` phase and keyword hooks; work was
  **wiring localization**, not inventing a new pipeline stage from scratch.

## Outcomes (production-aligned)

Shipped backend behavior (see log) includes `modules/bird_detection.py`, `images.bird_bbox`, migration
`0033`, config section `bird_detection`, and later alignment with **image-scoring-model** defaults
(`bird_detect_v0.pt`, pad `0.10`, `imgsz` / `max_det`, EXIF-oriented inference path).

## Related

- [RESEARCH_SESSIONS_2026-08-05.md](RESEARCH_SESSIONS_2026-08-05.md) — later bird-crop research arc
- [bird-detection-recall-2026-09-07.md](bird-detection-recall-2026-09-07.md) — recall floor at default `imgsz=640`
