---
type: Report
title: "Pipeline streamlining: blockers, decisions and suggestions"
description: Status snapshot, blockers with unblock actions, a decision register covering every open question in specs 01–06 and rollout stage 4, a cost model, GPU sequencing, risks and prioritised suggestions.
resource: docs/specs/pipeline-streamlining/07-blockers-and-decisions.md
tags: [specs, pipeline, localization, scoring, blockers, decisions, risks]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
---

# Pipeline streamlining: blockers, decisions and suggestions

**Issue:** #417 · **Hub:** [INDEX.md](INDEX.md) · **As of:** 2026-09-25, `master` at `0863767`

This page collects what the specs leave open: blockers, decisions, numbers and risks. It
recommends; you decide. Figures cite their source. Anything marked **estimate** is arithmetic on
stated assumptions, not a measurement.

## 1. Status snapshot

| Item | State |
|---|---|
| Rollout stages 1–3 (#346, #370, #375, #377) | Closed. |
| Rollout stage 4 slice 1 (#387, PR #395) | **Closed but not finished.** Its [status doc](../../planning/localization-stage4-slice1-status.md) still lists five open questions and three action items; they are now tracked in **#414**. |
| #336 (`test_runs_autodrive.py` hangs with a live DB) | Fixed by #384. That removes one of stage 4's two blockers. |
| #399 (test DB never truncated) | **Open, p1, unassigned.** `truncate_app_tables` (`modules/db_postgres.py:283-305`) still inserts `TRUE` and Python booleans into the SMALLINT columns `enabled`, `optional` and `default_skip` (`:1034-1036`), then swallows the error with `except: pass`, which rolls back the `TRUNCATE`. |
| #379 (alembic missing; `POSTGRES_PORT=5433` pin) | Open. Postgres suites can **silently skip** instead of failing. |
| Specs 01–06 (#406–#409, #412, #413) | Merged as docs (#411). No implementation has started. |
| New from this review | #414 (stage 4 follow-ups), #415 (labelled bursts), #416 (timing baseline), #418 (unrotated thumbnails reach ML), gallery [#176](https://github.com/synthet/image-scoring-gallery/issues/176) (cross-repo notice). |

**Related open issues** that affect the pipeline's end states:
- #360: `image_keywords.relevance_weight` is the default 1.0 on 97.4% of rows.
- #368: parent/child lifecycle for delegated culling runs.
- #109 / #110: Lightroom recognition of pick/reject flags and ratings.

## 2. Blockers

| ID | Blocks | Evidence | Unblock action | Who | Issue |
|---|---|---|---|---|---|
| **B1** | Any trustworthy `-m postgres` result, and so M0 | Test DB rows leak between tests. The ordering-dependent failures seen in the #387 status doc follow from it. | Insert `1`/`0` instead of booleans, and log instead of `pass`. A one-line fix plus a regression test. | agent | #399 |
| **B2** | Believing a green Postgres run | Wrong port, or no alembic, leads to skips rather than failures. | Make the suite fail loudly when the DB is unreachable under `-m postgres`, and add alembic to the gpu-shell image. | agent | #379 |
| **B3** | Stage 5, and spec 04's crop backfill (needs current boxes) | The ~76k legacy outcomes were never imported. The import script exists (`scripts/import_legacy_localization.py`). | Dry run against production, compare with the 2026-09-22 survey, then run it live. | **you** (production DB) | #414 |
| **B4** | Stage 4's exit gate | Five open questions (§3.1). | Decide them; recommendations are below. | **you** | #414 |
| **B5** | Spec 04 promotion (AC-22) and within-burst ranking | 54 bursts gave CIs of ±0.05–0.09 ([probe](../../reports/subject-evidence-probe-2026-09-24.md)). About 300 are needed. | Count the existing independent human labels first (§4.4), then top up. | agent counts; **you** label | #415 |
| **B6** | Spec 03 adoption | The research ONNX weights came from a third-party product. | Export RTMDet-tiny from the upstream OpenMMLab checkpoint. That needs a one-off `mmdet`/`mmdeploy` toolchain outside the app environment. Record a manifest and re-run the comparison. | agent | #408 |
| **B7** | Spec 01 thumbnail switch; spec 04 migration | The gallery reads `image_model_scores` in `electron/db.ts`, `sortColumns.ts` and `sortSql.ts`. | The gallery adds `input_mode` filtering before the #409 migration ships. Thumbnail display is likely fine, because Chromium applies EXIF orientation by default. | gallery | gallery #176 |
| **B8** | Cost model, #409 backfill estimate, GPU sequencing | The only measured costs are #377's decode and YOLO timings. | Timing baseline on the 8 GB card. | agent (gpu-shell) | #416 |
| **B9** | Spec 06 beyond Aves | The source of the current `data/bird_species_list.txt` is undocumented. Other taxa need licence-compatible lists. | Document the bird list's source; choose per-taxon sources whose licence allows redistribution. | **you** + agent | #413 |
| **B10** | Cloud agents following the board contract | GraphQL and `projectsV2` are blocked from cloud sessions; the label sync (#390, #402) needs a token. | Add the `BOARD_SYNC_TOKEN` secret and run the dry run. | **you** | #390 |

## 3. Decision register

**Decide by** is the milestone that can't start until the decision is made. **Who**: "you" means
the maintainer. "Data" means the benchmark answers it, so a human only confirms.

### 3.1 Rollout stage 4 (#414)

| # | Question | Options | Recommendation | Decide by |
|---|---|---|---|---|
| S4-1 | Accept migration 0035 (`image_localization_runs.decode_route`)? | accept / move the route into `legacy_payload` | **Accept.** It's nullable, additive, already merged, and the route is part of rendition identity. | M0 |
| S4-2 | Is a `rawpy` failure caused by the environment (module missing) retryable? | terminal / retryable | **Retryable** with `error_code = environment_missing`. An operator can fix it without the source changing. A genuine decode failure stays terminal. | M0 |
| S4-3 | Should AC-14's reuse rule also cover `terminal_error`? | yes / no | **Yes, keyed on source hash.** Store the source hash on terminal runs (it's cheap, from `rendition.source_identity`), so an unchanged broken file isn't retried on every run. | M0 |
| S4-4 | Should a job with retryable per-image failures end `failed`? | failed / completed with failures reported | **Completed, with failures in the summary**, until the stage 7 repair lane exists. Failing the job now would make every detector outage look like a pipeline failure, with no repair path. Revisit with the repair lane. | M0 |
| S4-5 | Keep the 2048 px embedded-JPEG threshold? | keep / lower | **Keep for now.** #416 measures decode cost per route. The RTMDet arm ran on an ~800 px preview, so re-check once a cascade exists. | M2 |

### 3.2 Spec 01: rendition (#406)

| # | Question | Recommendation | Decide by |
|---|---|---|---|
| R-1 | Regenerate legacy thumbnails in bulk? | **Lazily in general, but regenerate portrait RAWs deliberately**, because #418 shows their unrotated pixels feed CLIP, BLIP and MobileNet. Regenerating changes the embeddings, so it's done together with an embedding-space version bump. | M1 |
| R-2 | Rendition JPEG quality 90, or PNG? | **90**, subject to AC-12's parity gate. PNG would be about 5× the disk for no demonstrated benefit. | M1 |
| R-3 | Cache non-RAW JPEG sources too? | **No.** Read them directly, with `bake_orientation` on read. Caching would duplicate files already on disk. | M1 |

### 3.3 Spec 02: phase graph (#407)

| # | Question | Recommendation | Decide by |
|---|---|---|---|
| G-1 | Two phase codes (`culling` + `selection`), or one code with a pending-picks state? | **One code first.** It avoids a cross-repo `phase_code` contract change while the flag proves the split. Promote to two codes only if completeness predicates get tangled. | M1 |
| G-2 | Keep `bird_species` behind `keywords`? | **Yes, until rollout stage 5** moves its scope to regions. Then relax the edge to `localization` (attempt-before) plus the scene route. | M3 |

### 3.4 Spec 03: detector cascade (#408)

| # | Question | Recommendation | Decide by |
|---|---|---|---|
| C-1 | Refine IoU (0.3) and padding (1.0)? | **Data.** Sweep IoU {0.2, 0.3, 0.5} × pad {0.5, 1.0, 2.0} on `det_small` and the COCO-only small boxes, and grade tightness with the LLM panel. | M2 |
| C-2 | When both detectors fire, keep the COCO boxes as extra regions? | **No, YOLO only**, for continuity with `bird_bbox`. Revisit with multi-subject (spec 04, O-3). | M2 |
| C-3 | Test the agreement arm (YOLO box only if COCO also sees an animal)? | **Yes. It's the cheapest false-positive filter known:** −13 of 28 YOLO false positives, 100/101 true detections kept. | M2 |
| C-4 | Operating point: the default policy is 17% false positives, over AC-18's 10% | **Data.** Sweep the threshold. Either the matched-recall point (4%) or the agreement arm must pass AC-18. | M2 |

### 3.5 Spec 04: subject-aware scoring (#409)

| # | Question | Recommendation | Decide by |
|---|---|---|---|
| O-1 | α, γ, crop padding? | **Data, and never tuned on the evaluation split.** Fit on the training folders of #415, report on held-out folders. | M4 |
| O-2 | Reduced α for `region_small` rather than 0? | **0 until labels say otherwise.** The probe found crop focus below chance on small subjects. | M4 |
| O-3 | SPAQ (MUSIQ/TF) on crops? | **Not initially.** It adds a TensorFlow pass per image. Reconsider after #416 prices it, and only if the three PyTorch models leave a measurable gap. | M4 |
| O-4 | Expose `image_composite_scores` through the API? | **Yes, read-only, before promotion**, so v1 and v2 can be compared in the gallery. It's an OpenAPI change, and follows the cross-repo workflow. | M4 |
| O-5 | How to tell a user-set XMP rating from a pipeline-written one (AC-20)? | **Store the last pipeline-written rating per image** (a new column) before the rewrite job exists. Without it AC-20 can't be implemented, because the app writes XMP ratings itself (`modules/xmp.py`). | M4 |

### 3.6 Spec 05: scene route (#412)

| # | Question | Recommendation | Decide by |
|---|---|---|---|
| SR-1 | Single-label or multi-label? | **Store all probabilities and route on the top label.** Multi-label adds nothing to routing. | M2 |
| SR-2 | CLIP ViT-B/32 or OpenCLIP ViT-L/14? | **Data. Benchmark both**, and report what fraction of the library has each vector. L/14 exists only where two-level culling ran. | M2 |
| SR-3 | Route `people` to a person detector? | **Later, as a separate spec.** Out of scope until wildlife routing is proven. | after M4 |
| SR-4 | Build on vectors computed from unrotated thumbnails? | **Fix #418 first**, or benchmark on corrected vectors. Otherwise portrait RAWs are classified sideways. | M2 |

### 3.7 Spec 06: species beyond birds (#413)

| # | Question | Recommendation | Decide by |
|---|---|---|---|
| SP-1 | Where do species lists come from? | Document the current bird list's origin first. For other taxa, prefer regional checklists whose licence allows redistribution, and record source and licence per list. | M3 |
| SP-2 | Keep the `bird_species` code, or add `species`? | **Keep `bird_species` with a taxon dimension** until at least one non-bird taxon is approved. A rename is a cross-repo contract change for no user benefit yet. | M3 |
| SP-3 | Insects and herps without a detector? | **Data.** Benchmark full-frame accuracy first. If it's poor, park those taxa until an open-vocabulary detector is benchmarked. | M3 |
| SP-4 | `taxon:*` keywords? | **Prediction rows only at first**, with `species:*` keywords as today. Add a taxon facet if the gallery asks for it. | M3 |

## 4. Details

### 4.1 Cost model

**Measured** (#377, RTX 4060 Laptop, 8 GB, `image-scoring-gpu-shell`):

| Step | p50 | p95 |
|---|---:|---:|
| Decode (`open_rendition_for_ml` + RGB + `bake_orientation`) | 507 ms | 774 ms |
| YOLO-640 | 146 ms | 366 ms |
| YOLO-1280 | 194 ms | 388 ms |
| RTMDet-tiny, CPU, ~800 px preview (research workstation, [comparison](../../reports/subject-detector-comparison-2026-09-24.md)) | 95 ms | 117 ms |

**Decodes per RAW today** (code paths):
1. Thumbnail generation (`generate_thumbnail`).
2. Scoring prep (`convert_raw_to_jpeg` writes a temp JPEG per image).
3. Localization (`decode_for_localization`).
4. Bird species (`_resolve_inference_path` prefers the original RAW).

Keywords and clustering read the thumbnail. That makes **4 decodes per bird RAW and 3 per other
RAW**, which spec 01 reduces to one.

**Estimate:** 2–3 avoided decodes × ~0.5 s ≈ **1.0–1.5 s saved per RAW**, or about **2.8–4.2
hours per 10,000 RAWs**. This assumes every avoided decode costs about #377's p50; #416 replaces
the assumption with per-route measurements.

**Crop backfill (spec 04) — estimate, illustrative only.** It is 41,001 boxes (the stage 2 survey) × 3
models × *t*, where *t* is the per-crop latency, which isn't measured yet. At *t* = 100 ms that's
about 3.4 GPU-hours; at *t* = 300 ms, about 10.3. Crops reuse the models already loaded for
full-frame scoring, so there's no extra model-load cost.

**Rendition cache disk — estimate.** About 0.5–1 MB per 2048 px JPEG at quality 90, so roughly
**50–100 GB per 100k images**. That's why the cache is bounded (`rendition.cache_max_gb`, default
50) and regenerable (spec 01, AC-5, AC-6).

### 4.2 GPU sequencing on 8 GB

Runs already execute phases one after another (`pipeline_orchestrator.py`), and the operator rule
forbids running heavy ML in `webui` and `gpu-shell` at the same time. Within that model:

1. **Keep RTMDet on CPU** (onnxruntime). At 95 ms p50 it doesn't need the GPU, and that leaves VRAM
   free for YOLO and BioCLIP.
2. **Only one phase's models resident at a time:**
   - localization: YOLO, which peaks at 59 MiB allocated at 640;
   - then species: BioCLIP;
   - then scoring: the IQA models, as today, with the circuit breaker and per-image
     `empty_cache`;
   - then keywords: CLIP and BLIP.
3. **Crop scoring adds no model loads.** It's a second forward pass through the models scoring
   already holds, which is why spec 04 puts it inside the scoring worker and not in a separate phase.
4. Peak VRAM per model isn't known beyond YOLO; #416 measures it before anyone considers keeping
   two phases' models loaded together.

### 4.3 Migration risk matrix

| Change | Spec | Reversible? | Blast radius | Guard |
|---|---|---|---|---|
| `images.thumbnail_version` | 01 | yes (nullable) | backend only | additive |
| `image_model_scores.input_mode` + primary-key change | 04 | **hard**: a PK change on a large table, read by about 20 backend modules and 3 gallery files | cross-repo | audit readers first (B7); default `full_frame`; ship the reader filters **before** the migration |
| `image_composite_scores` | 04 | yes (new table) | backend | additive |
| `images.score_fusion_version`, last pipeline-written rating | 04 | yes | backend, and XMP indirectly | nothing rewrites until an operator job runs |
| `image_scene_labels` | 05 | yes (new table) | backend | additive |

The only hard migration is spec 04's primary-key change. An **alternative worth weighing**: keep
`image_model_scores` untouched and store crop scores in a sibling table,
`image_region_model_scores`. That avoids the PK change and the reader audit entirely, at the cost
of one extra join in fusion v2. **Recommendation: take the sibling table**, unless a single table
is needed for a reason not yet found.

### 4.4 Labelled bursts: count before collecting

The existing independent human signal (`modules/score_analytics/labels.py`) is `culling_picks`
with `auto_suggested = 0`. Auto-cull `pick_status` (`cull_policy_version` set) is leakage. XMP
picks and ratings are unverified, because the app writes them too. A read-only count of usable
bursts:

```sql
-- groups a human reviewed in a culling session, with at least one human pick and one human reject
SELECT COUNT(*) AS usable_bursts
FROM (
  SELECT cp.session_id, cp.group_id
  FROM culling_picks cp
  WHERE cp.auto_suggested = 0 AND cp.group_id IS NOT NULL
  GROUP BY cp.session_id, cp.group_id
  HAVING SUM(CASE WHEN cp.decision = 'pick' THEN 1 ELSE 0 END) > 0
     AND SUM(CASE WHEN cp.decision = 'reject' THEN 1 ELSE 0 END) > 0
) s;
```

Session groups are what the human actually reviewed. They may not match today's `stacks`, because
re-clustering changes stack membership. Group by `images.stack_id` instead only when the
evaluation must use current stacks, and report both counts.

**Human effort — estimate:** at 30–60 s per burst, 300 bursts is **2.5–5 hours**, less whatever
the count above already covers. Stratify by subject-size tercile, and split by folder so tuning
(O-1) and evaluation never share a folder.

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Score drift** from new rendition pixels | medium | high: anchors calibrated on about 61k images shift | Spec 01 AC-12 parity gate; scoring stays on the old path until it passes |
| **False boxes contaminate subject scores** | high with YOLO-1280; medium with the cascade | high | Spec 03 AC-18 false-positive gate before any consumer; agreement arm (C-3) |
| **Star-rating churn** in XMP and Lightroom | certain once v2 is promoted | high: user-visible | Operator-triggered rewrite with dry-run counts (spec 04 AC-18, AC-19); keep user-set ratings (O-5); verify with #109/#110 |
| **Scene false skips** (small bird in a landscape) | medium | medium | Skip only at high confidence (spec 05 AC-4, ≤ 2% wildlife skipped) |
| **Label leakage** from pipeline-written XMP or auto-cull | high if not guarded | high: inflated gains | Use only `auto_suggested = 0` picks plus new labels (§4.4); folder-grouped splits |
| **Mixed embeddings** after fixing orientation (#418) | certain if fixed in place | medium | Version the embedding spaces or re-embed; never mix |
| **Cache disk growth** | medium | low | Bounded, regenerable cache (spec 01 AC-5, AC-6) |
| **Cross-repo breakage** (`image_model_scores` readers) | medium | high | Sibling table (§4.3), or ship reader filters first (gallery #176) |
| **Third-party weights** slip into production | low once B6 is done | high: licence and provenance | Weights manifest check (spec 03 AC-1, AC-2) |

## 6. Suggestions, most value per effort first

1. **Fix #399 now.** It's a one-line value change plus a visible `except`, and every Postgres result
   depends on it.
2. **Run the legacy import dry run (#414).** It needs no code and unblocks stage 5 and the crop
   backfill.
3. **Run the §4.4 count before building any labelling UI.** The count may already cover part of #415.
4. **Ship spec 02's keywords edge as its own tiny PR.** Tags stop waiting for scoring immediately.
5. **Fix #418 together with spec 01**, not separately. Both change thumbnail pixels, so one
   embedding-version bump covers them.
6. **Use the sibling table for crop scores (§4.3)** instead of changing `image_model_scores`'s
   primary key. It removes the riskiest migration and most of B7.
7. **Bootstrap box-quality labels with the LLM panel** ([report](../../reports/bbox-llm-judge-panel-2026-09-24.md)).
   It's 95% correct on the verifiable subset; send only split and audit boxes to a human.
8. **Harvest manual deletions** (XMP sidecars without a NEF) as candidate rejects, verified before use.
9. **Keep RTMDet on CPU**, and tie its onnxruntime dependency to the ONNX plan
   ([ONNX_CONVERSION_FEASIBILITY.md](../../planning/models/ONNX_CONVERSION_FEASIBILITY.md)), so
   there's one ONNX runtime decision, not two.
10. **Keep Jev off the critical path.** Every spec here works without it, consistent with the
    rollout's text-evidence boundary.

## 7. Next actions

- [ ] #399: fix the truncation bug (agent).
- [ ] #414: decide S4-1 to S4-5 (you); run the dry-run legacy import (you).
- [ ] #415: run the §4.4 count (agent), then label the remainder (you).
- [ ] #416: timing baseline in gpu-shell (agent).
- [ ] #418: measure the portrait-RAW share and its impact (agent).
- [ ] B10: add `BOARD_SYNC_TOKEN` and dry-run the label sync (you).
- [ ] Decide §4.3: sibling table versus a primary-key change (you), before #409 starts.

## Related

- [INDEX.md](INDEX.md) — spec hub and roadmap
- [planning/pipeline-streamlining.md](../../planning/pipeline-streamlining.md) — the plan
- [planning/localization-stage4-slice1-status.md](../../planning/localization-stage4-slice1-status.md) — the stage 4 questions in §3.1
