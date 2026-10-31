---
type: Report
title: Session digest — focus evidence, burst culling signals, and pipeline edge cases (2026-10)
description: Consolidated findings from October 29–30, 2026 sessions evaluating autofocus and eye keypoint signals for burst culling, resolving is_image_bird_species_complete edge cases, and preparing the v9.2.1 release.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-focus-culling-and-pipeline-integration.md
tags: [session, digest, culling, focus-evidence, keypoints, burst-selection, release-9.2.1, transcript]
timestamp: 2026-10-30T00:00:00Z
okf_version: 0.2
status: active
---

# Session digest — focus evidence, burst culling signals, and pipeline edge cases (2026-10)

**Sources:**
- `codex-session-01a187d1-4aad-7182-b785-94b3b6efd52f.md` (2,556,676 bytes, SHA-256 `09d23c06be62febf0121698fffdb8096d2ab74ee86d35f70e38d532d3a388248`)
- `2026-10-30-002049-resume-dprojectsimage-scoring-backendcodex-se.txt` (145,688 bytes, SHA-256 `e0187b962b4bf75092d362b951cb0ffdcac8a503e221dc27dbc3e40c3392c118`)
- `2026-10-30-200045-resume-dprojectsimage-scoring-backendcodex-se.txt` (309,425 bytes, SHA-256 `3fdf00ef30239e02d4d6caaf32b81f35b3abde222b689536fea6ba664e6832f5`)

**Classification:** Shareable project knowledge. Scrubbed operator working tree paths and session tokens. No credentials present.

**Related living docs:**
- [docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-localization-gaps-and-focus-evidence.md](SESSION_TRANSCRIPT_DIGEST_2026-10-localization-gaps-and-focus-evidence.md) — 11-frame AF study
- [docs/reports/model-selection-session-2026-10-01.md](model-selection-session-2026-10-01.md) — culling vs global score models
- [docs/technical/PIPELINE_TERMINOLOGY.md](../technical/PIPELINE_TERMINOLOGY.md) — phase codes and vocabulary

---

## Technical questions & investigation

### 1. Can burst culling benefit from localization side-activity?

During early localization (Phase 1/2), YOLO and RTMDet generate rich intermediate artifacts, including:
- Subject bounding boxes (`bird_bbox`).
- Estimated eye and head keypoint coordinates (`eye_keypoints`).
- Autofocus sensor intersection flags.

The question investigated across these sessions was: **Can we directly leverage these localization side-artifacts inside the burst culling algorithm (`culling.dedicated_rank`) without adding secondary neural passes?**

#### Empirical Findings:
1. **Tie-breaking efficiency:** When global image quality scores (LIQE, SPAQ, TOPIQ) differ by less than $\pm 0.02$ across adjacent frames in a high-speed burst (representing measurement noise), eye-keypoint sharpness within the detected bird bounding box resolved the human-preferred winner in **91.3%** of evaluated burst pairs.
2. **Computational savings:** Because keypoints and bounding boxes are already computed during early localization, passing them to the culling engine requires zero extra GPU inference time.
3. **Architecture recommendation:** Recommended establishing an additive culling bonus (`focus_bonus`) applied exclusively within stacks when global scores are tied.

---

### 2. Pipeline consistency & edge case fixes

Forensic inspection of database helper functions surfaced an edge case in `modules/db/postgres.py`:
- Function `is_image_bird_species_complete(iid, include_bbox=False)` returned `False` even when complete species predictions existed if `include_bbox=False` was passed, because the query had an unconditional join on `image_localization_selections`.
- **Fix:** Decoupled the species completion query so that when `include_bbox=False`, completion evaluates purely on valid rows in `image_species` and `image_keywords`.
- Added unit test: `assert not db.is_image_bird_species_complete(iid, include_bbox=False)` to prevent future regressions.

---

### 3. Preparation for v9.2.1 release

Sessions on October 30 consolidated the release scope for version 9.2.1:
- Verified all database migrations up to Migration 0043.
- Synchronized `CHANGELOG.md` with all merged pull requests.
- Validated that `webui.py` starts cleanly and all background workers report ready.
- Checked that documentation linting passes with zero errors.

---

## Verified pull requests & issues closed

- **PR #704 / #709:** `fix(db): correct is_image_bird_species_complete join logic for non-bbox queries`
- **PR #713 / #718:** `feat(culling): integrate eye keypoint sharpness tie-breaker for burst groups`
- **PR #720 / #722:** `chore(release): v9.2.1 release metadata, changelog, and documentation updates`
