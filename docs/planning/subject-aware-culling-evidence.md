---
type: Plan
title: Subject-aware culling evidence — consolidated with the localization rollout
description: Clean-room plan for region-, keypoint- and mask-conditioned quality evidence, a code-owned within-burst ranker, and burst sub-segmentation, mapped stage by stage onto the eight-stage localization rollout.
resource: docs/planning/subject-aware-culling-evidence.md
tags: [planning, culling, localization, evidence, scoring, keypoints, saliency, bursts, clean-room]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
status: proposed
---

# Subject-aware culling evidence

> **Status:** proposal, no code written. Every item below lands **inside a stage of the
> [early localization rollout](../architecture/pipeline/localization-rollout.md)** and obeys its
> rollout invariants. Nothing here changes production scores, culling or keywords before the
> relevant stage gate. Since 2026-09-25 the pipeline-level design lives in
> [pipeline-streamlining.md](pipeline-streamlining.md) (#410) and its
> [spec hub](../specs/pipeline-streamlining/INDEX.md); this page keeps the evidence, ranker and
> explainability parts. Where each idea is tracked is in
> [Consolidation with pipeline streamlining](#consolidation-with-pipeline-streamlining-2026-09-25).

Companion pages:

- [models/subject-evidence-model-roles.md](models/subject-evidence-model-roles.md) — what each model
  must do (function, I/O, open candidates)
- [within-burst-evidence-plan.md](within-burst-evidence-plan.md) — Arm A/B crop IQA plan, which this
  page extends with non-IQA evidence

Cross-repo counterparts:

- image-scoring-model: `docs/architecture/eye-evidence-spec.md`
- image-scoring-gallery: `docs/features/planned/burst-culling-explainability.md`
- image-scoring-skills: `docs/burst-judge-quality-evidence.md`
- image-scoring-ui: `docs/scoring-evidence-tokens.md`

## Consolidation with pipeline streamlining (2026-09-25)

The [pipeline-streamlining plan](pipeline-streamlining.md) adopted several ideas from this page and
the 2026-09-24 reports, and turned them into specs and issues. This table is the single map of
where each idea now lives, so the two documents don't drift.

| Idea (this page) | Now owned by | Notes |
|---|---|---|
| Working + fine renditions, resampler identity | Spec 01, #406 | One ~2048 px inference rendition replaces the separate ~800 px working and ~1600 px fine renditions. Evidence code derives its working size from that rendition by a recorded, uniform-scale resize, so the "resize fit is part of identity" lesson still applies. |
| Open COCO detector as second provider, targeted small-box pass | Spec 03, #408 | Cascade YOLO-640 → COCO animal → small-box YOLO refine; upstream OpenMMLab weights only. |
| Region IQA in scoring | Spec 04, #409 | Crop IQA fused into `score_technical` (fusion v2). |
| Subject-conditioned **named evidence** and bands | #423 | Complements #409: per-criterion, explainable, feeds the ranker and gallery reasons. |
| Continuous-burst sub-segmentation (~0.5 s) | #424 | Finer unit inside stacks; pairs with #407's split of grouping from picks. |
| Labelled bursts (roadmap step 0) | #415 | Note: `culling_picks` holds **no** usable human decisions today (all 3,374 non-auto rows have `decision IS NULL`). |
| Species: list gaps, abstention, burst/folder suggestions | #422 | Birds now; #413 extends to other taxa and should reuse the abstention rule. |
| Keyword selection by calibrated per-tag thresholds | #420 | Also the recommended rule for the scene route (#412). |
| Florence-2 captions (shadow) | #421 | Plugs into the caption backend factory (#152). |
| Timing for every stage | #416 | Replaces the CPU timings quoted in the reports. |

## Ideas elaborated

**1. Evidence as features, then a learned within-burst ranker.** Fusion v2 (#409) blends crop IQA
with fixed weights. Once #423 shows which criteria carry within-burst signal, the useful ones can
enter a *learned* pairwise ranker: a logistic model on within-burst differences
(`Δfocus`, `Δeye`, `Δcrop_technical`, …), trained on a folder-grouped split of the #415 bursts and
evaluated on a held-out split. This beats hand weights only if it wins the same best-vs-reject
paired bootstrap that gates fusion v2 (spec 04 AC-21/22). Keep fixed weights as the fallback.

**2. Agent panels as a labelling multiplier.** The blind multi-agent panels were 95% correct on the
verifiable subset for boxes and self-consistent at 83–92% for species
([bbox panel](../reports/bbox-llm-judge-panel-2026-09-24.md),
[species panel](../reports/keywords-captions-species-comparison-2026-09-24.md)). For #415 and for
box-level labels, let a panel pre-label, and send the owner only the split verdicts plus a random
~10% audit. Two rules carry over:
- blind the candidates (random A/B, no manifest in the judges' folder);
- any text judge (Jev) uses a rubric that matches the vision rubric word for word. A mismatched
  rubric cut agreement from 82% to 66%.

Agent verdicts stay labelled as agent-derived and never replace owner labels in a promotion gate.

**3. One small-subject policy everywhere.** Three results point the same way:
- crop focus fell below chance on the smallest subject tercile (evidence probe);
- the open detector clips small birds (28/48 TIGHT);
- spec 04 already sets `region_small` below 2% of the frame or 224 px.

Use one threshold for all three consumers (evidence limitation `small_subject`, fusion α = 0,
cascade refine trigger), defined once in config and recorded in each artifact's provenance.

**4. Evidence invalidation follows rendition identity.** Evidence rows key on region id, rendition
hash and extractor version, like crop scores in spec 04 (AC-14). A new rendition route (#406) or
detector version (#408) therefore invalidates evidence without a library rescan, and the recompute
is crop-local.

## Provenance (clean-room)

This page comes from a competitive analysis of a commercial wildlife burst-culling application. The
sources were its user documentation and its observable input/output behaviour (scores and
explanations shown to the user for known frames).

It describes **what the system should do**. It contains no source code, internal identifiers, file
layouts or model weights from that product, and it names no proprietary model. Proprietary
components are described by function only.

Numbers given below are behavioural starting points, to be re-fitted on our own labels. They are not
constants to copy.

Implementers work from this page, our own code and open literature. If a behavioural comparison
against the commercial app's exported results is used, it serves as a black-box sanity check only,
never as training labels.

## Why this belongs in the localization epic

What we already know:

| Finding | Source |
|---|---|
| Whole-frame IQA is flat within a burst (SPAQ 72–77, LIQE 74–95 over 60 frames) | [within-burst plan](within-burst-evidence-plan.md) |
| Classical blur measures on the **full frame** score at chance on real misses (best AUC 0.53) | `modules/focus_quality.py` docstring |
| Crop IQA is 2.4–17.5× more sensitive to subject degradation, but no culling gain was shown yet | [crop study](../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md) |
| Jev failed because *"pairwise visual differences were not supplied"* | [epic, Stage 6](../architecture/pipeline/localization-rollout.md) |

The reference design solves exactly this problem. It **never judges the frame; it judges the subject.**
Every measurement is conditioned on the subject:
- the subject region
- head and eye keypoints inside that region
- a subject mask inside that region

Frames are then compared **inside one burst** by deterministic code.

In the epic's terms, this is a concrete design for:
- the **Stage 6 "visual evidence extractor"**, at scope `region` and `stack`
- the **Arm B ranker** of the four-arm table

The epic already reserves the slot. This page fills it.

## Reference design, described by behaviour

1. **Working renditions.**
   - The embedded RAW preview is the fast decode route.
   - A *working* rendition (~800 px long edge) feeds detection, mask, exposure and composition.
   - A larger greyscale *fine* rendition (~1600 px long edge) is used only for sharpness measurements
     on the subject and the eye.
2. **Subject localization.**
   - A general multi-class detector returns several boxes.
   - The primary subject is chosen by confidence weighted by box area. This avoids picking a
     confident but tiny background animal.
   - Only animal classes count as subjects.
3. **Keypoints inside the primary region.**
   - Birds: a bird-specialised head/eye keypoint model (function in
     [model roles](models/subject-evidence-model-roles.md#bird-headeye-keypoints)).
   - Mammals: a general animal-pose model.
   - A heuristic fallback runs when the models are unconfident.
   - A **targeted second pass** re-runs keypoints on a higher-resolution crop when the subject is
     small.
4. **Subject mask.** Salient-object segmentation of the frame, intersected with the primary box.
5. **Semantic embedding.** A CLIP-style image embedding drives zero-shot scene labels (in flight,
   perched, on water, captive/feeder, …) and species suggestions.
6. **Six evidence criteria**, then a weighted composite, a monotonic calibration curve and a burst
   ranking with explicit tie handling.

Negative observations are data, not failures:
- **No subject found:** the composite is capped rather than zeroed, and flagged.
- **Animal with no verifiable eye/head:** a multiplicative penalty applies in the ranker, and a
  reason is shown.

This matches the epic invariant that `no_detection` is a versioned observation.

## Stage-by-stage mapping

| Epic stage | Idea | What it adds | Guardrail from the epic |
|---|---|---|---|
| **2** persistence | Region-linked **derived artifacts**: keypoints and masks | `image_region_keypoints` (region id, provider key/version/config hash, point name, normalized display-space x/y, confidence, visibility) plus a mask artifact referenced by content hash (coverage stats in the DB, pixels in the cache). Zero keypoints is recorded as an outcome row, not as absence. | One run row per attempt; absence never means "not attempted". |
| **3** rendition | **Working + fine rendition sizes**; resampler identity | Add resampler kernel, fit mode (uniform scale, letterbox), output size and colour→grey policy to `RenditionDescriptor`. Model inputs use **uniform-scale letterboxing**; anisotropic scaling silently shifts keypoints and boxes. See [determinism lessons](#determinism-lessons). | Crop keys change when any provenance input changes (already an exit gate). |
| **3** detector benchmark | **Targeted second pass for small subjects** | The benchmark showed global 1280 px lifts eagle recall 20→53/59 but turns 35/54 verified negatives into false detections. The reference runs a higher-resolution pass **only inside an already-found region**, for keypoints. Evaluate the same pattern as the "targeted second-pass candidate" already named in Stage 3. | Production defaults unchanged until the benchmark. |
| **3/4** primary selection | **Area-weighted primary** | Consumers pick the primary region by `confidence × f(area)`, not confidence alone. Detectors still persist all regions ranked by confidence; primary choice is a *consumer policy* with a version. | "Multiple detections retained; consumers decide." |
| **4** shadow phase | **Keypoint and mask providers** | Extra providers in the `localization` phase, run only for images with a current region and versioned like the detector. Preferred-before `scoring`. | Failures never block core phases. |
| **5** BioCLIP | **Burst propagation and folder shortlist** | A confident region-level species on one frame is proposed to burst-mates that lack a confident prediction. Build a per-folder "suggested species" list from aggregated top-k. Both are suggestions, never auto-written keywords. | Preserve existing species results unless refresh is requested. |
| **6** evidence | **Six-criterion evidence extractor** (scope `region`) + **pairwise stack evidence** (scope `stack`) + **named bands** | See [evidence specification](#evidence-specification-stage-6-scope-region). Stored as evidence artifacts / research JSONL. **Not** in `image_model_scores` until it gains an input-mode dimension. | Full-frame production score stays authoritative. |
| **6** technical failures | Subject-region metrics | `technical_failures` gains separately named `subject_*` metrics (focus in mask, clipping in mask, background noise) next to the global ones. | Matches the Stage 6 consumer-policy row. |
| **6** ranker | **Code-owned composite + within-burst ranking** | This is Arm B's ranker. Jev (Arm C) may only consume the same evidence afterwards. | Arithmetic and thresholds stay in code. |
| **7** backfill | Evidence is cheap once a region exists | Compute evidence only for explicitly requested and sampled folders. No library-wide evidence backfill. | "Backfills boxes, not scores." |
| orthogonal | **Burst sub-segmentation** | See [burst segmentation](#burst-segmentation). Defines the `stack` scope for pairwise evidence. | Group-scoped judgments are invalidated when membership changes. |

## Evidence specification (Stage 6, scope `region`)

Each criterion emits raw measurements, a 0–100 sub-score, a **named band** and a
**limitations** list. Raw values stay in the durable record; only bands are model-visible (epic,
Stage 6).

| # | Criterion | Measure | Band examples |
|---|---|---|---|
| 1 | **Subject focus** | Noise-corrected sharpness (reuse `focus_quality.py`: Immerkaer sigma, bounded blur ratio) on the fine rendition inside **mask ∩ box**. Also measure head region when keypoints exist, and background outside the mask. Report subject/background ratio (back-focus detector). | `tack_sharp`, `sharp`, `slightly_soft`, `soft`, `missed_focus`, `background_sharper` |
| 2 | **Eye visibility and sharpness** | From eye keypoints: visible count, confidence, facing (both, profile, away). Measure eye-patch sharpness on the fine rendition, with patch size scaled to head size, **relative to head/subject sharpness in the same frame**. Details in the model repo's eye spec. | `eye_sharp`, `eye_soft`, `eye_not_visible`, `head_unverified` |
| 3 | **Exposure on subject** | Mean subject luminance against a target band. Highlight clipping fraction inside the mask, with small speculars exempt. Shadow crush in the mask. Frame-level clipping carries less weight. Subject-vs-background luminance separates backlit from underexposed. | `well_exposed`, `subject_dark`, `highlights_clipped`, `backlit` |
| 4 | **Noise** | Robust sigma (MAD/Immerkaer) on flat background patches outside the mask, combined with an **ISO prior per camera model**. The prior is fitted from our own library as sigma vs ISO, grouped by `Model`. Without a subject, fall back to whole-frame flat patches. | `clean`, `visible_noise`, `heavy_noise` |
| 5 | **Composition** | Subject fill fraction (too small, ideal, too tight). Edge clipping (mask touches the frame edge = cut-off). Head/eye placement vs thirds and centre, with **look-room** (facing direction toward open space). Background clutter (edge density outside the mask). | `good_fill`, `subject_small`, `cut_off`, `no_look_room`, `busy_background` |
| 6 | **Context** | Zero-shot scene label (scene sets the expected fill: in-flight tolerates small fill, portrait expects tight fill). Our existing CLIP quality head (`modules/clip_quality.py`, pick/reject AUC 0.89) serves as the context signal instead of new prompts. | `in_flight`, `perched`, `captive_context`, … |

**Stack scope (pairwise).** For each burst, compute per criterion:
- the rank and z-score within the burst
- the gap to the burst best
- the pairwise difference to the current best

This is the "pairwise visual differences" evidence the Jev report found missing.

**Limitations are explicit:**
- `no_region`
- `region_suspicious_geometry`
- `mask_low_confidence`
- `keypoints_heuristic`
- `small_subject_second_pass`

## Composite and ranker (code-owned, Arm B)

- **Weighted sum** of sub-scores. Starting weights to re-fit:

  | Criterion | Weight |
  |---|---|
  | focus | 0.28 |
  | eye | 0.22 |
  | exposure | 0.17 |
  | composition | 0.17 |
  | noise | 0.11 |
  | context | 0.05 |

  Presets re-weight, for example sharpness-first or composition-first. **Technical only** drops
  composition and context and renormalises.
- **No subject:** cap the composite and flag it; the flag is never folded silently into the number.
- **Head unverified** (an animal with no verifiable eye or head): a multiplicative penalty,
  starting at ×0.85, applied in the ranker and listed as a reason.
- **Calibration:** a monotonic piecewise-linear curve (isotonic fit) from composite to keep
  probability, fitted on human `pick_status` labels. Coordinate with
  [#185 calibration layer](models/CALIBRATION_LAYER_185_STATUS.md). One layer, not two.
- **Recomputable:** sub-scores and weights-version are persisted, so the composite can be re-derived
  client-side. The gallery "Adjust scoring" feature depends on this, without re-running inference.
- **Burst ranking:**
  - best = max composite, ties broken by eye sub-score, then filename (deterministic)
  - **nearly tied** = ≥ 2 frames within 5 points of the best: surface it for a human, don't pretend
    to decide
- **Confidence separation (epic invariant):** detector confidence, evidence confidence and decision
  confidence stay separate fields and are never multiplied together.
- **Reasons:** the strongest two positive and two negative bands become human-readable reason chips.
  Reason text is generated from bands by code, not by an LLM.

## Burst segmentation

- Stacks today use a 120 s gap, BurstUUID or visual clustering. That is *scene* grouping.
- Add a **continuous-burst sub-segmentation**: split a stack wherever the capture-time gap exceeds
  ~0.5 s. `SubSecTimeOriginal` is already extracted (`modules/exif_extractor.py`), so no new EXIF
  work is needed.
- A sub-burst becomes the `stack` scope for pairwise evidence and the unit for best-frame and
  nearly-tied.
- Stack RAW+JPEG pairs by basename before segmenting, so a pair never appears as two frames.
- The threshold is a versioned config value. Membership change invalidates group-scoped judgments
  (epic, Stage 6).

## Determinism lessons

These came up while validating the behavioural model. Each one silently moved results by several
points:

1. **Resize fit semantics.** "Fit inside", "cover" and "letterbox" use **one scale for both axes**.
   Only an explicit "fill" stretches axes independently. Mixing them up misaligns every box and
   keypoint. Record the fit in the rendition descriptor.
2. **The resampler library is part of identity.** Different libraries (PIL, libvips, OpenCV) give
   different pixels for the same nominal Lanczos resize, enough to change sharpness bands. Record
   library and version.
3. **Normalise model inputs in float64, then cast to float32.** This gave bit-identical embeddings
   across runs and platforms. Doing it in float32 did not.
4. **Pin the inference runtime version** (e.g. onnxruntime). Execution provider choice (CPU vs
   DirectML) made no measurable difference, but runtime versions did.
5. **Per-model execution-provider opt-out.** Some graphs (large CLIP) are unreliable on DirectML.
   All DirectML sessions in a process must share **one global lock**; concurrent sessions crashed.
6. **Evidence version invalidates caches.** Bump the extractor version whenever a criterion changes,
   and drop dependent embedding caches. Stale caches produced false regressions.
7. **Trace switch.** An env var that dumps every criterion's intermediates per frame as JSON. Add a
   one-frame **diagnostics bundle** export (overlays + JSON) for bug reports.

## Evaluation (folder-grouped, epic four-arm table)

| Arm | Evidence | Decision |
|---|---|---|
| A | existing whole-frame scores | current ranker |
| B | A + six-criterion region evidence + pairwise stack evidence | composite/ranker above |
| B′ | B minus one criterion at a time | ablation → keep/drop per criterion |
| C | exactly B's evidence | Jev (only if B beats A) |

**Labels:**
- `images.pick_status` (human) is primary.
- Agent label sets (image-scoring-skills `bird-crop-label`) are secondary and never counted as human
  truth.

**Metrics:**
- pick/reject AUC and within-burst concordance, via the existing `score_analytics` router
- best-frame hit rate and nearly-tied rate
- per-criterion within-burst AUC

**Slices:**
- small subject
- `no_detection`
- in-flight
- multi-subject
- backlit

**Gates:**
- A criterion is **displayed** in the gallery only if its folder-grouped within-burst AUC CI lies
  above 0.5.
- The composite is **promoted** only if Arm B beats Arm A with a CI-excluded difference.
- Focus is the riskiest criterion given the chance-level full-frame result. The hypothesis under
  test is that *region-conditioned, burst-relative* focus separates frames where full-frame focus
  did not.

### Measured so far

See the [subject-evidence probe, 2026-09-24](../reports/subject-evidence-probe-2026-09-24.md). It
covered 236 agent-labelled frames in 54 bursts.
- Overall, B ≈ A (composite 0.574 vs AVA 0.574, paired difference CI ±0.09). The composite is the
  only feature whose CI excludes chance.
- On best-vs-reject pairs, B leads: composite 0.669, subject focus 0.625, against ≤ 0.563 for Arm A.
- Small subjects are at chance for everything.
- Within a burst, exposure and context carry no signal.
- `images.pick_status` is **not** usable as ground truth. It mirrors `cull_decision`, which is
  derived from `score_general`.

## Roadmap (ordered by value ÷ cost)

| # | Item | Stage | Size | Depends on |
|---|---|---|---|---|
| 0a | **Open COCO detector as a second localization provider** (#408) (shadow; upstream weights). It beat YOLO-1280 on the #377 cohort ([comparison](../reports/subject-detector-comparison-2026-09-24.md)) | 3–4 | S–M | upstream checkpoint re-run |
| 0 | **Human label set** (#415): about 300 bursts of pick/reject, stratified by subject-size tercile (no human labels exist today) | — | M (your time) | — |
| 1 | Descriptor addendum: resampler, fit, working/fine sizes (folded into #406) | 3 | S | — |
| 2 | Evidence extractor v0 (#423) using the **imported `bird_bbox` regions** only: focus, exposure, noise, composition from box, no mask yet → research JSONL | 6 | M | Stage 2 import |
| 3 | Burst sub-segmentation (0.5 s) as stack scope (#424) | orth. | S | — |
| 4 | Arm A vs B evaluation + per-criterion ablation | 6 | M | 2, 3 |
| 5 | Mask provider (salient-object model) in shadow; switch focus/exposure to mask ∩ box | 4 → 6 | M | 4 shows signal |
| 6 | Keypoint provider: our eye-pose model for birds, open animal-pose for mammals, targeted second pass | 4 → 6 | L | model repo eye spec |
| 7 | Sub-score + reasons API (`/api/images/{id}/evidence`), weights-version, recomputable composite | 6 | M | 4 gate |
| 8 | Species on BioCLIP (#422): expanded vocabulary, abstention (similarity floor + margin), burst propagation, folder shortlist (suggestions only). General CLIP is **not** a species model ([comparison](../reports/keywords-captions-species-comparison-2026-09-24.md)) | 5 | S–M | Stage 5 |
| 9 | Feed evidence bands into agent judges (Arm C / skills) | 6 | S | 4 gate |

## Out of scope

- Any licensing or activation behaviour of the commercial app.
- Copying its code, identifiers, fitted tables or weights. We fit our own ISO prior and calibration.
- Changing production full-frame scores or culling before the Stage 6 gates pass.

## Related pages

- [Early localization rollout](../architecture/pipeline/localization-rollout.md)
- [Region scores and backfill](localization-region-scores-and-backfill.md)
- [Within-burst evidence plan](within-burst-evidence-plan.md)
- [Technical failure detection plan](models/TECHNICAL_FAILURE_DETECTION_PLAN.md)
- [Calibration layer #185](models/CALIBRATION_LAYER_185_STATUS.md)
