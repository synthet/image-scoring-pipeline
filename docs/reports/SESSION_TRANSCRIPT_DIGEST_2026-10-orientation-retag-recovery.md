---
type: Report
title: Session digest — RAW portrait orientation bug, keyword ownership, and retag recovery (2026-10)
description: Consolidated findings and operational record from October 16–17, 2026 sessions resolving issue 418 (EXIF orientation ignored in RAW thumbnails for CLIP/BLIP), fixing keyword ownership data-loss bug 586, and recovering job 6945 after host sleep.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-orientation-retag-recovery.md
tags: [session, digest, orientation, keywords, issue-418, issue-586, job-recovery, operations, transcript]
timestamp: 2026-10-17T00:00:00Z
okf_version: 0.2
status: active
---

# Session digest — RAW portrait orientation bug, keyword ownership, and retag recovery (2026-10)

**Sources:**
- `2026-10-16-194859-this-session-is-being-continued-from-a-previous-c.txt` (166,894 bytes, SHA-256 `5c607e9a6c2af7462aaee0f63c08ad171c2bfab30f477b215024be0c3c2c4c09`)
- `2026-10-16-214720-this-session-is-being-continued-from-a-previous-c.txt` (245,316 bytes, SHA-256 `5122a9b4f1c462aefa488b817ef46bb2ff711e7eea2edc35adddbf44b87bcfab`)
- `codex-session-01a14807-3f4a-70c3-88da-7364c6f70714.md` (403,072 bytes, SHA-256 `6b760d2c1835c237b142d8eb6f2948378d0ba5e2cd306893df9cffb72a88571e`)
- `2026-10-17-214618-command-messageresume-taskcommand-message.txt` (65,411 bytes, SHA-256 `697632048369673d09374de360a6c9dd30b27e68f2acc524097bca309b829e77`)

**Classification:** Shareable project knowledge. Scrubbed operator home directories, LAN IPs, and session UUIDs. No credentials present.

**Related living docs:**
- [docs/reports/retag-418-session-2026-10-17.md](retag-418-session-2026-10-17.md) — job 6945 execution summary
- [docs/reports/SESSION_TRANSCRIPT_DIGESTS.md](SESSION_TRANSCRIPT_DIGESTS.md) — digests router
- [docs/technical/BIRD_SPECIES_WALKTHROUGH.md](../technical/BIRD_SPECIES_WALKTHROUGH.md) — species walkthrough

---

## Root problem & dependencies

### 1. Issue #418: RAW portrait orientation bypass

Portrait-oriented RAW images (EXIF orientation tags 6 and 8, representing 90° and 270° rotations) were decoded into thumbnails where orientation tags were discarded. Consequently, CLIP and BLIP neural tagging models received sideways images, resulting in degraded caption quality and missing semantic tags. Fixing this required re-tagging 2,324 affected portrait images under Job 6945.

### 2. Issue #586: Keyword ownership data-loss bug

A critical blocker prevented immediately re-running the keywords phase: existing code performed a blunt `DELETE FROM image_keywords WHERE image_id = ?`, wiping **all** keywords for an image—including hand-curated labels and predictions written by other models (e.g. BioCLIP species keywords).

During a prior execution on 2026-10-09, 1,048 legitimate keyword rows were inadvertently deleted. Job 6945 had to remain strictly paused until:
1. The keyword ownership model was refactored (PR #626, issue #586) so that re-runs only overwrite keywords belonging to the active model source.
2. The 1,048 deleted keyword rows were fully restored from snapshot `backups/issue418-retag-20261016/`.

---

## Technical discoveries & operational recovery

### 1. Host sleep vs job crash

Job 6945 was interrupted twice: at 02:54 UTC and 05:02 UTC on 2026-10-17. Diagnostic inspection revealed:
- Containers exited with code 137, while PostgreSQL exited cleanly with code 0.
- Windows System Event Log confirmed Kernel-Power Event 42 (system sleep) and Modern Standby entries (506/507).
- The bind mount dropped as the Windows host entered sleep, causing `[Errno 5] Input/output error: '/app/config.json'` inside the container, marking the job status in PostgreSQL as `failed`.

### 2. Job restart endpoint semantics

Attempts to call `POST /api/runs/{id}/resume` failed because the router strictly requires `paused` or `interrupted` status. For a `failed` run, calling `/api/runs/{id}/retry` would generate a new job ID, abandoning completed progress.

**Finding:** The proper in-place recovery for a `failed` job is `POST /api/jobs/{id}/restart` (`restart_failed_job`). It preserves the existing job ID, retains completed phases, resets incomplete phases, and maintains `skip_done=True`.

### 3. Keep-awake script signed integer bug

The PowerShell `windows-keep-awake` script threw an exception on launch:
PowerShell parses hex literals `0x80000003` and `0x80000000` as negative 32-bit signed integers (`Int32`), failing the Windows Win32 API signature for `SetThreadExecutionState(uint)`. Casting with `[uint32]` literals resolved the failure.

---

## Outcome & verification

- **Restoration audit:** `verify_restore.py` verified that all 1,048 lost keyword rows were successfully restored prior to resuming.
- **Job completion:** Job 6945 finished terminal at 20:33:49 UTC on 2026-10-17:
  - 2,233 images successfully processed (`done`).
  - 90 images `skipped` with verified status `caption_only_no_keywords` (none had pre-existing keywords).
  - 0 failed `job_image_actions`.
- **Checkpoint verification:** `check_retag_checkpoint.py` verified that all 2,323 surviving images possess captions, no hand-entered rows were altered, and 0 species labels were lost.
- **Issue closure:** Issue #418 was updated with full forensic evidence and closed as completed.

---

## Shipped PRs & operational rules

- **PR #626 (closes #586):** Scoped keyword ownership deleting only rows matching the calling generator source.
- **Rule:** Never use `resume` on a `failed` job; use `POST /api/jobs/{id}/restart`.
- **Rule:** Unattended batch processing on Windows requires active `display-required` thread execution states to suppress Modern Standby.
