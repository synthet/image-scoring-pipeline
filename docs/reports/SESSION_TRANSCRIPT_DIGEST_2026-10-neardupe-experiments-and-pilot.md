---
type: Report
title: Session digest — near-duplicate burst culling, variance decomposition, and Lightroom XMP soft-culls (2026-10)
description: Consolidated findings from October 15–31, 2026 sessions resolving the zero-yield paradox in burst near-duplicate culling, decomposing spatial variance, implementing non-destructive Lightroom Classic XMP soft-culls, and executing the E7 pilot.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-neardupe-experiments-and-pilot.md
tags: [session, digest, neardupe, culling, burst-selection, variance-decomposition, lightroom-xmp, e7-pilot, transcript]
timestamp: 2026-10-31T00:00:00Z
okf_version: 0.2
status: active
---

# Session digest — near-duplicate burst culling, variance decomposition, and Lightroom XMP soft-culls (2026-10)

**Sources:**
- `codex-session-01a144c3-96d5-7532-993d-bd9029ac9f8a.md` (550,221 bytes, SHA-256 `1dbc3ad2dd0646fba785c48cb4cbd62783e6f37bb812a195151c0683c4c99ab6`)
- `codex-session-01a147ac-9cd3-73d1-912b-5344bbf474ec.md` (483,328 bytes, SHA-256 `4ce4836e81a875c1c0c2fe06f352b417a3f26d8f4dc7a7154451de88bad2a6ee`)
- `codex-session-01a14806-82b8-7d63-986a-bcc3b7f037bc.md` (261,120 bytes, SHA-256 `28afa6616de66a6e214b49187853a1b2578190061f4678b7ce2174531189b08c`)
- `codex-session-01a150e1-d3bc-74b2-bb79-8f59a1a12569.md` (945,152 bytes, SHA-256 `4349da0de9ee090d64d1ac1e2347877e2deee353b151021e030fb6ba3a49ee45`)
- `2026-10-29-235502-command-messageresume-taskcommand-message.txt` (563,200 bytes, SHA-256 `3911da6b0234f40562d1f0229df63a566340cb710eedf2df14cba3c888e9d6d3`)
- `2026-10-30-200055-this-session-is-being-continued-from-a-previous-c.txt` (230,400 bytes, SHA-256 `7fcbffc64f4c4680f6d424641d5256372d99c0107cf3549b152a6024a23436ea`)
- `2026-10-31-122006-local-command-caveatthe-command-below-was-run-d.txt` (211,968 bytes, SHA-256 `d78ea9b2d428e295dfa5fdcda0ab4391b435c2cbea94cd455f61b4bfc5108684`)

**Classification:** Shareable project knowledge. Scrubbed operator paths and session IDs.

**Related living docs:**
- `docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-focus-culling-and-pipeline-integration.md` — keypoint tie-breaking
- `docs/reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md` — baseline culling rubrics
- `scripts/neardupe_study/experiments/e7pilot.py` — pilot execution harness

---

## Technical Questions & Empirical Findings

### 1. Root Cause of the Zero-Yield Paradox in Near-Duplicate Culling

Across initial evaluations of burst culling runs, conventional pixel-difference, perceptual hashing, and SSIM metrics produced **zero cull recommendations** on high-speed wildlife bursts that were visually near-identical.

#### Empirical Analysis:
1. **Rigid Window Failure:** Algorithms compared fixed bounding box crops. In wildlife photography (e.g., small songbirds at 20–30 fps), subtle camera shake and subject respiration cause high localized pixel displacement between frames.
2. **Motion Parallax Dominance:** Decomposing total image variance demonstrated that frame-to-frame difference was dominated by background parallax and subject micro-shifts rather than compositional differentiation.
3. **The Solution:** Developed the `paired-physical-v3-envelope`. By incorporating sub-pixel shift alignment (x/y compensation) and comparing variance within soft physical envelopes, near-duplicate detection successfully identified redundant frames with zero false-rejection of distinct behavioral poses.

---

### 2. Lightroom Classic Non-Destructive Soft-Cull Schema

Automated culling pipelines previously risked user catalog corruption or data loss when proposing culls via file movement (e.g., moving images to `_removed/`).

#### Discovery & Verification:
1. Inspected Adobe Lightroom Classic (Lrc) catalog and sidecar interaction.
2. Verified the non-destructive pick/reject flag schema in `.xmp` sidecars:
   ```xml
   <xmpDM:pick>-1</xmpDM:pick>
   ```
3. Setting `<xmpDM:pick>-1</xmpDM:pick>` marks the photo as **Rejected (`X`)** in Lightroom Classic upon metadata read, while keeping `<xmpDM:pick>1</xmpDM:pick>` for Flagged (`P`) and `0` for Unflagged (`U`).
4. This preserves the underlying raw files untouched on disk, keeps catalog paths intact, and allows photographers to filter by rejected flags in Lightroom with one keystroke (`Ctrl+Backspace`) to delete or review.

---

### 3. Experiments E0 through E7 and E7 Pilot Rollout

The near-duplicate research track progressed through eight discrete experimental phases:
- **E0–E2 (Baseline Calibration):** Established pairwise SSIM and perceptual hash baselines on controlled bursts.
- **E3–E4 (Variance Decomposition):** Separated camera-motion variance from subject pose variance.
- **E5 (Boundary Formulation):** Integrated edge synthesis and sub-pixel shift compensation.
- **E6 (Cross-Camera Generalization):** Validated threshold stability across Nikon Z8/Z9 high-speed RAW files.
- **E7 (Production Pilot):** Implemented in `scripts/neardupe_study/experiments/e7pilot.py`, delivering automated paired proposals with sidecar XMP injection.
