---
type: Technical Reference
title: Region scores, bbox backfill, and parallel full-frame vs crop storage
description: Synthesis of planned backfill for bird regions vs region IQA scores, and how full-image and crop scores are stored today vs in the localization rollout.
resource: docs/planning/localization-region-scores-and-backfill.md
tags: [planning, localization, bird-detection, scoring, database, backfill]
timestamp: 2026-09-23T00:00:00Z
okf_version: 0.1
---

# Region scores, bbox backfill, and parallel full-frame vs crop storage

Authoritative rollout design: [architecture/pipeline/localization-rollout.md](../architecture/pipeline/localization-rollout.md).  
Current schema pointers: [technical/DB_SCHEMA.md](../technical/DB_SCHEMA.md), [architecture/pipeline/phases/scoring.md](../architecture/pipeline/phases/scoring.md).

## Backfill: boxes vs region scores

Two different “backfills” are in play; only one is on the near-term roadmap.

### Localization / bbox (yes, staged — not a blind full-library rescore)

[Early localization rollout](../architecture/pipeline/localization-rollout.md) **Stage 7** defines controlled repair and backfill:

1. **Import** existing `images.bird_bbox` (boxes + `{"detected": false}` sentinels) into normalized tables **without** re-running the detector (76,086 outcomes in the 2026-09-22 live survey: 41,001 boxes + 35,085 sentinels; the older crop-study snapshot had 66,485).
2. New / source-changed images.
3. Targeted repair (`birds` keyword gaps, retryable errors, conflicts).
4. Explicit folder requests, then sampled legacy population, then wider expansion only after cost/quality gates.

Stage 4+ shadow localization explicitly must **not** change production scores until later stages approve it. The [rollout supplement](../architecture/pipeline/localization-rollout-supplement-2026-09-08.md) also says **broad legacy backfill** and **authoritative crop/fusion** stay **disabled** until benchmarks pass.

**Operational today:** detector-only backfill, not crop IQA:

- `scripts/backfill_bird_bbox.py` — YOLO only, writes `bird_bbox` (or sentinel), no BioCLIP, no scoring on crops ([BIRD_SPECIES_WALKTHROUGH](../technical/BIRD_SPECIES_WALKTHROUGH.md)).

### Region / crop IQA scores (no production backfill plan yet)

- Bird-crop research ([#317](https://github.com/synthet/image-scoring-backend/issues/317)) ran offline (`scripts/research/bird_crop/`, `reports/bird-crop/`). It did **not** productionize crop IQA; culling showed **no** crop benefit; agent labels are explicitly **not** human ground truth ([research sessions hub](../reports/RESEARCH_SESSIONS_2026-08-05.md)).
- **Stage 6** adds optional experiments behind `scoring.subject_crop_shadow` — **non-authoritative** crop IQA; production composites stay **full-frame**.
- The [within-burst evidence plan](within-burst-evidence-plan.md) re-scores crops in **research JSONL** and states **`image_model_scores` stays untouched**.

**Summary:** **yes** for planned bbox/localization import + bounded repair; **no** committed plan to backfill **parallel region IQA** into production tables until Stage 6 gates pass (and even then shadow-first, not “replace full-frame everywhere”).

---

## How parallel full-image vs crop scores would be stored

### Today (production)

| Concern | Storage |
|--------|---------|
| Box geometry | `images.bird_bbox` JSONB (authority); normalized `image_localization_runs` + `image_regions` (migration 0034) but **dormant** until `localization.read_normalized_first` |
| Full-frame model scores | `image_model_scores` — PK **`(image_id, model_name)`**, plus aggregates on `images` (`score_general`, etc.) |
| Experimental models | Same table, `is_shadow = true` (excluded from fusion / scoring completeness) |

There is **no** `region_id` or `input_mode` on `image_model_scores` yet, so you **cannot** store both “LIQE on full frame” and “LIQE on bird crop” as two first-class production rows without a schema change.

### Target design (Stage 5–6, not fully DDL’d)

The rollout separates **geometry** from **inference provenance**:

```text
image_localization_runs  →  image_regions  (boxes + run provenance)
         ↓
rendition + CropPolicy  →  crop bytes (cache), on demand
         ↓
consumers record input mode: full_frame | region | fusion
```

Every experimental score is supposed to carry provenance: **region id**, crop-policy version, model version, fusion version, rendition/source hashes (Stage 6 mode contract in [localization-rollout.md](../architecture/pipeline/localization-rollout.md)).

### Consumer policy (authoritative vs shadow)

| Consumer | Planned behavior |
|----------|------------------|
| Production IQA / `score_general` | **Full frame only**; region IQA **shadow-only** |
| `images` composite columns | Stay full-frame–derived until a consumer-specific promotion gate |
| Technical / focus | Full-frame globals + **separately named** subject-region metrics (e.g. `focus_quality` behind disabled `technical_failures`) — not the same as duplicating the MUSIQ/LIQE stack |
| Embeddings / culling | Full frame only; region embeddings are a **different identity** |
| BioCLIP (Stage 5) | Region-first with full-frame fallback; **record input mode** on new predictions; today can mix inputs into one image-level embedding space |

### Research path until promotion

- Crop re-scores → **JSONL / reports**, not `image_model_scores`.
- When shadow crop IQA is wired, the natural fit with today’s model is **`is_shadow = true`** rows **plus** a future key dimension (e.g. `region_id` / `input_mode` or extended PK). That migration is **not** in the tree yet; Stage 6 only requires provenance on outputs and shadow isolation from production fusion.

### Practical implication

- **Parallel scores** are a **Stage 6+** concern: same logical models, different **input mode** and **region**, stored so completeness predicates and gallery still treat **non-shadow full-frame** `image_model_scores` as “scoring complete.”
- **Parallel boxes** are **Stage 2/7**: normalized regions + import of legacy `bird_bbox`, not re-inference of ~76k outcomes by default.

## Related issues and epics

- Localization epic **#345**; Stage 2 normalized persistence **#370**.
- Bird-crop / focus research **#317**.
