---
type: Report
title: Session digest — localization Stage 5 rollout and shadow validation (2026-10)
description: Consolidated record of October 11–15, 2026 sessions completing the 4,401-image shadow comparison, resolving the 9p ExifTool timeout bug, evaluating Stage 5 multi-agent promotion gates, and shipping geometry-only promotion for small crops.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-localization-stage5-shadow.md
tags: [session, digest, localization, stage-5, shadow-run, exiftool, bioclip, gates, transcript]
timestamp: 2026-10-15T00:00:00Z
okf_version: 0.2
status: active
---

# Session digest — localization Stage 5 rollout and shadow validation (2026-10)

**Sources:**
- `2026-10-11-004821-read-the-recently-created-docs-and-resume-locali.txt` (82,023 bytes, SHA-256 `f20e4843fcccf0a714db0d1851770c50da626595a9dca2f9a21bf17ba7185dbc`)
- `2026-10-11-102407-read-the-recently-created-docs-and-resume-locali.txt` (124,190 bytes, SHA-256 `e3bc158536088b97ac19c883199699d94ddb3b5ad306352e13d4697564d8cb1b`)
- `2026-10-11-222303-read-the-recently-created-docs-and-resume-locali.txt` (132,078 bytes, SHA-256 `16d59ce4e538ad4799a921d33d2f35e858ae697a66a44b9cc5c55c0309188320`)
- `2026-10-12-080221-read-the-recently-created-docs-and-resume-locali.txt` (133,146 bytes, SHA-256 `051541cd51b86ef5564f0a4fd16afab9abeefa50cd3a638b41ddca032a39b26a`)
- `2026-10-15-204253-read-the-recently-created-docs-and-resume-locali.txt` (212,048 bytes, SHA-256 `49d864c41a57de8e17e9f4a01e833367254b3386f38e4fb61e3c41827ea4b19d`)
- `codex-session-01a13035-3589-7e93-af28-9c12d8f19e95.md` (460,274 bytes, SHA-256 `1574fb7f036fd13cf1eded7c912cb65dd9b03e5550475da37010544007980050`)
- `codex-session-01a1388d-8b41-7f23-ae71-1e52d3952e94.md` (1,060,725 bytes, SHA-256 `2a990cdc4259825fd6df293219ae82df8eb09b50aa42d4ac9157e622c1ad7fe1`)
- `codex-session-01a1388d-8b41-7f23-ae71-1e52d3952e94_2.md` (1,060,725 bytes, SHA-256 `2a990cdc4259825fd6df293219ae82df8eb09b50aa42d4ac9157e622c1ad7fe1`, identical snapshot)
- `codex-session-01a1388d-8b41-7f23-ae71-1e52d3952e94_3.md` (1,945,955 bytes, SHA-256 `da66bedd30812f50e707be5c698cea4bd466f1e3a596c9c877a36195154ee6f7`)

**Classification:** Shareable project knowledge. Scrubbed internal workstation paths and agent session IDs. No live credentials present.

**Related living docs:**
- [docs/reports/localization-session-work-log-2026-10-10.md](localization-session-work-log-2026-10-10.md) — shadow comparison work log
- [docs/reports/localization-species-policy-validation-2026-10-10.md](localization-species-policy-validation-2026-10-10.md) — aggregate policy validation
- [docs/architecture/pipeline/localization-rollout.md](../architecture/pipeline/localization-rollout.md) — status of record
- [docs/reports/localization-rollout-summary-2026-10-22.md](localization-rollout-summary-2026-10-22.md) — 8-stage summary

---

## Problem & context

Stage 5 of early localization represents the transition where downstream species classification stops running on full frames and begins consuming detected, gated region crops.

Before promoting Stage 5 to production, three critical gates had to be evaluated:
1. **Gate A (#592):** Region BioCLIP on the 4,401 selections previously promoted under rule/3 (#472).
2. **Gate B (#593):** Small-stratum bounding box geometry promotion under rule/4.
3. **Gate C (#408):** Secondary detector cascade evaluation.
4. **G5c Small-Species Quality:** Whether species predictions on small crops meet the $\ge 0.85$ precision threshold.

---

## Technical challenges & diagnostics

### 1. 9p mount ExifTool timeouts

During execution of Partition 1 (2,200 images), thumbnail generation repeatedly hit 10-second timeouts inside Docker when invoking `exiftool -b -JpgFromRaw` across the Windows-to-WSL 9p filesystem boundary.

**Resolution:**
- **Short-term:** Instrumented an in-memory / local staging buffer bounded to 128 MiB, decoupling single-model inference from 9p read jitter.
- **Production fix (PR #592, commit `32c4a0a1`):** Updated `modules/thumbnails.py` to define `EXIFTOOL_TIMEOUTS = (10, 60)` in `_exiftool_embedded_jpeg()`, retrying intermittent slow reads once with a 60-second limit before giving up. Added unit tests in `tests/test_thumbnails_exiftool_retry.py`.

### 2. Missing `birds` keyword audit

Auditing the 4,401 frozen selections revealed that 546 images lacked a baseline `birds` keyword row in `image_keywords`. Running a species update on rows lacking this keyword would have caused silent exclusions in downstream queries that filter on `birds`.

**Resolution:** The operator script repaired these 546 rows by inserting the missing baseline `birds` tags before executing the species refresh.

---

## Gate evaluation & promotion outcomes

The multi-CLI agent panel (incorporating Gemini, Claude, and Codex with Jev adjudication) evaluated the promotion gates:

| Gate | Target cohort | Criterion | Observed metric | Disposition |
|---|---|---|---|---|
| **Gate A (#592)** | 4,401 large/medium selections | Agreement & precision on validated crops | Zero skips, 100% parity on test subset | **PASSED (Promoted)** |
| **Gate B (#593)** | Small-box geometry (rule/4) | Box validity & non-empty intersection | 128/128 boxes resolved accurately | **PASSED (Promoted)** |
| **Gate C (#408)** | Detector cascade | AC-17 & AC-18 detector recall | Passed acceptance criteria | **PASSED (Promoted)** |
| **Gate G5c** | Small-crop species classification | Precision lower bound $\ge 0.85$ | $0.8123 < 0.85$ | **FAILED (Blocked)** |

### Production decisions shipped (October 15, 2026)

1. **Large & medium selections live:** 4,401 large/medium boxes were promoted to active region BioCLIP (`bird_species.use_regions = True` for gated selections).
2. **Small boxes promoted as geometry-only:** The 274 small bounding boxes passing Gate B were promoted into `image_localization_selections` for visual and geometry consumers, but species classification **abstains** on small crops due to the Gate G5c failure.
3. **Detector cascade enabled:** Issue #408 cascade was enabled for secondary box generation.
4. **Legacy column safety:** `images.bird_bbox` continues to serve as the read projection, ensuring backward compatibility with older UI and API consumers.

---

## Pull requests & commits landed

- **PR #592 (commit `32c4a0a1`):** `fix(thumbnails): retry an ExifTool embedded-JPEG timeout once (#592)`
- **PR #593:** `feat(localization): Stage 5 rule/4 small-box geometry promotion (geometry-only)`
- **PR #594:** `feat(pipeline): wire gated region crop into BioCLIPClassifier`
- **PR #598:** `test(localization): multi-judge acceptance suite for Stage 5 gates`
- **PR #608, #609, #612, #614, #615:** Downstream consumer and documentation alignments.

---

## Lessons learned

- Virtualized filesystem boundaries (such as 9p mounts between Windows and Linux Docker) introduce non-deterministic I/O latency that standard CLI tools with short hardcoded timeouts cannot absorb. Two-tier timeout retry structures (`10s -> 60s`) prevent spurious job failures.
- Decoupling geometry selection from feature classification allows valuable bounding boxes to be promoted and stored without forcing downstream models to consume noisy or low-resolution crops.
