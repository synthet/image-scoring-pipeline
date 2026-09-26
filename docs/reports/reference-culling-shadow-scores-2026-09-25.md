---
type: Report
title: Reference culling scores as shadow models — library-wide backfill and agreement analysis
description: A behavioural reimplementation of a reference wildlife-culling design scored all 76,822 on-disk library images. The 7 headline scores went into image_model_scores as shadow models; 93 scalar dimensions, structured records, bursts and embeddings went into a separate refcull schema. Its composite agrees with score_general at ρ 0.30 (existing models inter-correlate at a median of 0.40), eye evidence is the strongest link (ρ 0.41), and no-subject frames diverge. No human labels, so these are agreement measures only.
resource: docs/reports/reference-culling-shadow-scores-2026-09-25.md
tags: [research, culling, shadow-models, score-analytics, evidence, clean-room]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
---

# Reference culling scores as shadow models (2026-09-25)

> **Provenance:** derived from competitive analysis of a commercial application's observable behaviour
> and documentation; contains no code, identifiers, fitted constants or model artefacts from it. The
> scores come from **a local research instrument** (a behavioural reimplementation of a reference
> wildlife-culling design) run outside this repo on the owner's photos. Every number below is a
> **measurement, not a target**: production decisions must be re-measured with our own implementation and
> upstream weights.

Related: [subject-aware culling evidence](../planning/subject-aware-culling-evidence.md) ·
[subject-evidence probe](subject-evidence-probe-2026-09-24.md) ·
[human culling labels](../planning/human-culling-labels.md) ·
[score analytics](../features/implemented/11-score-analytics-and-model-suitability.md)

## What was done

1. Every folder in the `image_scoring` database was scored by the research instrument, from the RAW
   files. **76,822 of 76,831** images are covered; the other 9 files no longer exist on disk.
2. The instrument's per-image output was stored **by type**, so the dashboard stays small:

   | Where | What |
   |---|---|
   | `image_model_scores`, `is_shadow = TRUE` | Only the 7 headline scores: `refcull_focus`, `refcull_eye`, `refcull_exposure`, `refcull_composition`, `refcull_noise`, `refcull_context`, `refcull_composite`. These are the criteria the reference design shows its users. |
   | schema `refcull.image_dims` (long: image_id, dim, raw, normalized) + `refcull.dim_meta` | 93 scalar dimensions: the criteria, their sub-components, intermediate measurements, subject-detection geometry, eye/head evidence, scene class, flags, and burst rank / size / gap to best |
   | `refcull.image_records` (`jsonb`) | One structured record per image (box, eye points, facing, scene, flags, reasons, burst membership) |
   | `refcull.bursts` | 42,738 time-gap bursts (0.5 s split) with their best frame |
   | `refcull.image_embeddings` (`vector(512)`) | 75,767 CLIP ViT-B/32 image embeddings |

   The same data also exists as local files next to the instrument (CSV, JSONL, JSON, raw float32).
3. A standalone statistics script (no webui) compared the refcull dimensions with the production models
   and composites, across the library and inside backend stacks.

A database backup was taken before the import (`backups/postgres/image_scoring_20260925_125336.dump`).

**Safety.** Shadow rows are ignored by composites, culling, stack best-image selection and agent
payloads (all filter `is_shadow = FALSE`); only Score Analytics and image detail show them. Nothing in
the backend reads the `refcull` schema. Undo:

```sql
DROP SCHEMA refcull CASCADE;
DELETE FROM image_model_scores WHERE model_name LIKE 'refcull\_%';
```

## Normalisation to the production range

The production models store `normalized` in 0–1 with pooled mean ≈ 0.58 and SD ≈ 0.11 (the mean of the
8 models' means and SDs). Each refcull dimension was mapped onto that range:

- 0/1 dimensions are stored as is.
- Continuous dimensions get a **linear map to the pooled mean and SD**, clipped to [0, 1]. Strongly
  right-skewed positive ones (skew > 2) are `log1p`-transformed first.
- Both maps are monotone, so rank statistics (Spearman, AUC, top-1) are unchanged. The raw value is
  always kept in `raw_score` / `raw`, and the map's parameters are in `model_version` / `dim_meta`.

This is a presentation choice so the refcull curves sit on the same axis as the other models in Score
Analytics; it is not a calibration.

## Results

**Labels caveat.** The database has no independent human culling labels: `images.pick_status` and
`stacks.best_image_id` derive from `score_general`, and the 3,374 non-auto `culling_picks` rows carry no
decision. Everything below measures **agreement and structure, not accuracy**.

### Agreement with the library's scores

Spearman ρ across all images:

| refcull | general | technical | aesthetic | liqe | topiq | ava | spaq |
|---|---:|---:|---:|---:|---:|---:|---:|
| composite | 0.30 | 0.25 | 0.26 | 0.33 | 0.24 | 0.33 | 0.08 |
| eye | 0.31 | 0.29 | 0.24 | 0.32 | 0.23 | 0.21 | 0.14 |
| exposure | 0.26 | 0.26 | 0.17 | 0.29 | 0.21 | 0.04 | 0.16 |
| focus | 0.24 | 0.23 | 0.16 | 0.29 | 0.28 | 0.16 | 0.07 |
| context | 0.22 | 0.20 | 0.19 | 0.22 | 0.16 | 0.25 | 0.07 |
| composition | −0.01 | −0.07 | 0.09 | 0.01 | −0.03 | 0.28 | −0.07 |
| noise | −0.03 | −0.08 | 0.03 | −0.01 | −0.07 | 0.16 | −0.06 |

For scale, the 8 production models correlate with each other at a median ρ of 0.40 (range −0.09 to
0.66). The reference design measures something **largely different** from whole-frame IQA; its
composition and noise criteria are nearly orthogonal to every production model except AVA.

### Strongest single dimensions

Over all 93 dimensions, the strongest links to `score_general` are subject evidence, not whole-frame
quality:

| Dimension group | ρ general | within-stack ρ |
|---|---:|---:|
| Eye-evidence base score / best eye-keypoint confidence | 0.41 | 0.27–0.33 |
| Subject box height, subject fill fraction | 0.31–0.34 | 0.26–0.32 |
| refcull composite | 0.30 | 0.32 |
| Composition "simplicity" component | −0.22 | −0.05 |

### Inside stacks (culling-relevant)

Spearman of ranks centred per backend stack:

| refcull | general | technical | topiq | liqe | ava |
|---|---:|---:|---:|---:|---:|
| composite | 0.32 | 0.30 | 0.34 | 0.23 | 0.28 |
| eye | 0.30 | 0.29 | 0.28 | 0.20 | 0.22 |
| focus | 0.19 | 0.16 | 0.17 | 0.12 | 0.20 |
| exposure | 0.03 | 0.06 | 0.09 | −0.03 | 0.01 |

Exposure varies between scenes, not between frames of one scene (ρ 0.26 across the library, 0.03 inside
stacks), so it carries almost no culling signal.

### Best-frame agreement

Share of stacks (11,146 with ≥ 2 frames) where a dimension's top frame equals `stacks.best_image_id`:

| Dimension | = stack best |
|---|---:|
| general (defines the best image) | 0.958 |
| liqe / spaq | 0.62 / 0.60 |
| topiq / paq2piq / koniq | 0.50 / 0.48 / 0.47 |
| refcull composite | 0.37 |
| refcull focus / eye | 0.38 / 0.36 |

The reference composite picks a different frame from the backend in about two stacks out of three.
Inside its own bursts, its eye score alone picks its composite's best frame 60% of the time.

### Grouping

The reference design splits bursts on a 0.5 s time gap: 42,738 bursts, 7,598 with ≥ 2 frames (mean size
1.8). 74% of those multi-frame bursts sit inside a single backend stack; the backend's 11,251 stacks are
coarser.

### By subject

| Subset | Frames | ρ(refcull composite, general) | mean refcull composite (0–100) |
|---|---:|---:|---:|
| all | 76,822 | 0.30 | 58.1 |
| no subject detected | 15,169 | −0.03 | 29.4 |
| bird | 45,446 | 0.31 | 67.0 |
| other subject | 15,152 | 0.33 | 63.5 |
| group shot | 3,200 | 0.17 | 70.0 |

Frames with no detected subject are capped low by the reference design, and there it no longer tracks the
backend at all. That is a design choice (no subject ⇒ not a keeper), not noise.

## What this means

- **Eye and subject-size evidence carry the overlap.** They are exactly the signals the
  [subject-aware evidence proposal](../planning/subject-aware-culling-evidence.md) adds; this is
  consistent with its Stage 6 shadow plan.
- **The disagreement is large enough to matter.** A best-frame match rate of 37% means the two approaches
  would keep different frames in most stacks. Which is right can only be settled with human labels.
- **Next step:** the [human culling label set](../planning/human-culling-labels.md) (#415). 302 groups
  are sampled and 20 are labelled; the evaluation will report per-group pairwise accuracy, top-1 and
  pick/reject AUC for every production model and every refcull dimension, re-weighted to the library.

## Reproduce

The instrument and statistics script live outside this repo (research workspace). From this repo, the
stored results can be inspected directly:

```sql
SELECT model_name, count(*), avg(normalized) FROM image_model_scores
WHERE model_name LIKE 'refcull\_%' GROUP BY 1;
SELECT dim, kind, meta->>'n' FROM refcull.dim_meta ORDER BY dim;
```
