---
type: Plan
title: Subject-evidence model roles
description: Functional requirements (inputs, outputs, failure behaviour) for the detector, keypoint, mask and embedding models behind subject-aware culling evidence; open candidates and our own assets.
resource: docs/planning/models/subject-evidence-model-roles.md
tags: [planning, models, localization, keypoints, saliency, clean-room]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
status: proposed
---

# Subject-evidence model roles

Parent plan: [subject-aware-culling-evidence.md](../subject-aware-culling-evidence.md).

This page is clean-room: each role is defined by **what the model must do**, not by any product's
implementation. Candidates are open-licence models or our own. Each role plugs into the localization
epic as a versioned provider or consumer. Provider/detector key, version and config hash are
persisted with every output.

## Subject detector

| | |
|---|---|
| Must do | Find every animal in the working rendition. Return boxes, classes and confidences, up to the configured cap. |
| Input | Working rendition, uniform-scale letterboxed to the model size. |
| Output | Unpadded boxes in normalized display space (epic, Stage 2). |
| Consumer policy | Primary subject = highest `confidence × f(area)`, restricted to animal classes. The policy is versioned and separate from the detector. |
| Failure behaviour | `no_detection` is an observation. Suspicious near-full-frame boxes are recorded, not rejected. |
| Ours | Existing bird YOLO (`modules/bird_detection.py`, `detect_boxes`). Cascade with the open detector: #408, [spec 03](../../specs/pipeline-streamlining/03-detector-cascade.md). |
| Open candidates | RTMDet-tiny (COCO, Apache-2.0). On the #377 cohort's YOLO-640 misses it reaches 82% recall at 4% FP (animal classes, ≥ 0.4), against YOLO-1280's 82% / 63%. It labels some raptors `bear`, so **class is a hint, not a gate**. See the [detector comparison](../../reports/subject-detector-comparison-2026-09-24.md). |

## Bird head/eye keypoints

| | |
|---|---|
| Must do | Given a crop around a bird, locate each **eye centre**, plus ideally bill tip and crown/nape. Give per-point confidence and a **visible/occluded** flag. |
| Robustness | Profile heads (one eye), tiny heads (< 40 px), partial occlusion by branches, motion blur, backlight, water reflections. It must not hallucinate an eye on a turned-away head: low confidence is the correct answer there. |
| Input | Primary-region crop (padded by a named crop policy) from the working rendition. **Targeted second pass**: when the head is small, re-crop from a larger rendition and re-run. |
| Output | Points in normalized display space, confidence, visibility, and the pass used (first/second). |
| Calibration | Confidence must be meaningful: a visibility gate that is well-calibrated on held-out data matters more than raw mAP. |
| Ours | `image-scoring-model` eye-pose model (YOLO-pose, CUB-200 bootstrap). See that repo's `docs/architecture/eye-evidence-spec.md`. |
| Training data | CUB-200-2011 part annotations (eyes, beak, crown, nape), plus our own hard cases: small heads, flight, occlusion. |

## Mammal pose

| | |
|---|---|
| Must do | Locate eyes, nose and ears (a 17-point animal skeleton is enough) for mammals in the primary region. Give per-point confidence. |
| Output | Same contract as bird keypoints. The eye points feed the eye criterion; the other points give head orientation (facing/look-room). |
| Open candidates | RTMPose/ViTPose trained on AP-10K (Apache-2.0). |
| Fallback | Heuristic head estimate from box geometry and the mask (top-of-mask extremum along the body axis), flagged `keypoints_heuristic`. |

## Subject mask

| | |
|---|---|
| Must do | Produce a soft foreground mask of the salient subject. It is intersected with the primary box, so it only needs to be good *inside* the box. |
| Output | 8-bit mask artifact (content-addressed, cached like crops) plus coverage stats: area fraction, edge-touch flags, mask confidence (mean foreground probability inside the box). |
| Use | Restricts focus, exposure and noise measurements to subject vs background. Edge-touch detects cut-off subjects. |
| Open candidates | U²-Net / U²-Net-p (Apache-2.0); a lightweight SAM variant prompted by the box, if the licence fits. |
| Failure behaviour | A low-confidence mask falls back to the box, flagged `mask_low_confidence`. |

## Semantic embedding

| | |
|---|---|
| Must do | Image embedding for (a) zero-shot scene labels that set composition expectations and (b) species suggestion. |
| Ours | Existing CLIP spaces and the CLIP quality head (`modules/clip_quality.py`); BioCLIP for species (Stage 5). |
| Rule | Full-frame and region embeddings never share an embedding identity (epic invariant). |

## Cross-cutting requirements

- Run inference in a pinned runtime version. Normalise inputs in float64, then cast to float32.
- Allow a per-model execution-provider opt-out, and serialise all DirectML sessions through one
  process-wide lock.
- Every output carries model key/version, config hash, rendition identity and crop-policy version,
  so staleness is computable (epic promotion checklist).
