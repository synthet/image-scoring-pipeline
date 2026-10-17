---
type: Report
title: Issue 418 re-tag recovery — session summary (2026-10-17)
description: Claude Code session that resumed and finished the job 6945 portrait re-tag for issue 418 after host sleep killed it twice; restart-vs-resume endpoint finding, progress timeline, verification results, follow-up decisions.
resource: reports/retag-418-session-2026-10-17.md
tags: [report, session, keywords, tagging, jobs, operations, issue-418]
timestamp: 2026-10-17T00:00:00Z
okf_version: 0.2
status: active
---

# Issue 418 re-tag recovery — session summary (2026-10-17)

**Source:** Claude Code terminal-text export of the session, 454 lines, original SHA-256 `f4d43024dd31855f3ca18977ecbe2231e86547bbda3c12e687c25852767b9b28`. The export ends at 17:56 UTC while the job was still running. The outcome sections below were observed later in the same session and are marked as such.

**Classification:** shareable project knowledge. The user's home-directory paths, agent session IDs and the second workstation's LAN address are removed. No credentials were present.

## Problem

Job 6945 re-tags the 2,324 portrait images affected by [#418](https://github.com/synthet/image-scoring-pipeline/issues/418) (rotated RAW thumbnails reaching CLIP and BLIP). It runs on the keyword-ownership fix from [#586](https://github.com/synthet/image-scoring-pipeline/issues/586) (PR #626), after the keywords the 2026-10-09 run deleted were restored (1,048 rows; receipt in `backups/issue418-retag-20261016/`).

The job had been interrupted twice when the whole Docker stack stopped, at 02:54 and 05:02 UTC on 2026-10-17. WebUI and gpu-shell exited with code 137 and were not killed for memory; Postgres exited 0. The previous session's run plan allowed one resume attempt, which the 05:02 stop used up.

## Findings and decisions

| Finding | Evidence | Decision |
|---|---|---|
| The host slept; the job did not crash | Windows System log: Kernel-Power event 42 (sleep) at 00:02 local, the 05:02 UTC stop, preceded by repeated 506/507 Modern Standby entries. AC sleep timeout was already "never" | Keep the host awake for the run (display-required execution state) |
| Job status was `failed`, not `interrupted` | `jobs.log` = `[Errno 5] Input/output error: '/app/config.json'` at 05:02:28 UTC. The bind mount dropped as the host went down, before the containers stopped | Treat as an environment failure, not a code fault |
| `POST /api/runs/{id}/resume` refuses `failed` runs | `modules/api/routers/electron_runs_lifecycle.py` accepts only `paused` and `interrupted`. `/api/runs/{id}/retry` creates a new job ID | Use `POST /api/jobs/{id}/restart` (`restart_failed_job`): same row and ID, completed phases kept, incomplete phases reset, `skip_done=True` kept from the earlier resume |
| The keep-awake skill script fails at startup | PowerShell parses `0x80000003` and `0x80000000` as negative Int32, which can't be passed as `SetThreadExecutionState(uint)` | Ran a fixed scratch copy using `[uint32]` literals; the skill itself was not edited in this session |
| The remote GPU runner timed out on every image | About 5 s of connect retries per image before the local fallback | Left alone during the run (see Outcome) |

A first attempt to read job 6945 at `/api/runs/6945` returned 404; the job row is at `GET /api/jobs/{id}`.

## Progress timeline (current attempt, restarted 16:22:23 UTC)

Measured as `image_phase_status` rows for `phase_id = 5` (keywords) with `job_id = 6945` updated since the restart, plus failed `job_image_actions`.

| UTC | Done | Skipped | Failed actions |
|---|---|---|---|
| 16:23 | 6 | 0 | 0 |
| 16:33 | 192 | 2 | 0 |
| 16:39 | 279 | 5 | 0 |
| 16:43 | 358 | 10 | 0 |
| 16:53 | 510 | 21 | 0 |
| 17:08 | 780 | 29 | 0 |
| 17:21 | 1,020 | 38 | 0 |
| 17:54 | 1,554 | 59 | 0 |
| 17:56 | 1,589 | 62 | 0 |

The rate was about 15–19 images a minute. Around 17:55 UTC Claude Code stopped its own background processes (the keep-awake and a status watcher) because the workstation was critically low on memory. The job itself kept running.

## Outcome (observed after the export ended, same session)

- **Job 6945 completed at 20:33:49 UTC.** All four phases `completed`, no phase error, 0 failed `job_image_actions`. Keywords phase: 2,233 `done` and 90 `skipped` of 2,323 existing images (the 2,324th no longer exists).
- **The 90 skips** are all `caption_only_no_keywords`: a caption was written, but CLIP produced no keyword above the threshold. None of the 90 had keywords before the run, so none lost any.
- **`verify_restore.py`** (against the 2026-10-09 snapshot): 791 species and hand-entered rows identical; 4 differ (newer region labels with the same species name, known); 0 hand-entered rows missing; 0 images lost their species label; 0 species-bearing images without `birds`.
- **`check_retag_checkpoint.py`:** all 1,048 restored rows present; 69 changed source or confidence, all of them `birds` rows re-emitted by CLIP; no restored species or hand-entered row changed. All 2,323 images now have a caption (1,201 before the resume).
- #418 was commented with these results and closed as completed.

### Follow-ups decided in the session

Jev (`jev-1.14.0`) was asked for each leftover question; host code and the user acted on its answers.

| Item | Jev answer | Disposition |
|---|---|---|
| Species refresh on the 592 restored images | Leave to the owner (p 0.84) | Deferred. BioCLIP was not affected by the orientation bug |
| `pre-onnxruntime-20261015` rollback image | Keep (p 0.55) | Kept |
| `stash@{0}` (pre-gate 382-name list) | Drop (p 0.88) | Dropped by the user. The same list is in `.agent/scratch/species-list-382/list382.txt` |
| gpu-shell container | Stop gpu-shell only (p 0.92) | Stopped by the user's request; it was later started again, likely by the `is-be-mcp` launcher |
| Remote GPU runner | Report only (p 0.53) | Investigated over SSH at the user's request: the runner host was hibernating (hibernate on AC after 3 h idle). It woke at 21:51 UTC and the runner container (restart policy `unless-stopped`) came back healthy. Hibernate on AC was set to never at the user's request |
| Walkthrough count | — | §5 of `docs/technical/BIRD_SPECIES_WALKTHROUGH.md` said 382 species; fixed to 379 ([#629](https://github.com/synthet/image-scoring-pipeline/issues/629), PR #630) |

## Lessons

- For an unattended Windows run, keep the display-required execution state. AC idle-sleep "never" does not prevent Modern Standby when the screen turns off.
- A host sleep can fail a job through a bind-mount I/O error before the containers stop. A `failed` status after a stack stop is not by itself evidence of a code fault.
- `resume` is for `paused` and `interrupted` runs only; `jobs/{id}/restart` is the in-place recovery for a `failed` run.
- The remote GPU runner host's own power settings matter: when it hibernates, every remote phase pays connect timeouts before the local fallback.

## References

- [`modules/api/routers/electron_runs_lifecycle.py`](../../modules/api/routers/electron_runs_lifecycle.py) — `resume_run`, `retry_run`
- [`modules/api/routers/tasks.py`](../../modules/api/routers/tasks.py) — `restart_job`
- [`modules/db_legacy.py`](../../modules/db_legacy.py) — `restart_failed_job`, `resume_job_phases`
- [`modules/tagging_image_processor.py`](../../modules/tagging_image_processor.py) — `caption_only_no_keywords` skip
- [Localization stage 5 activation](localization-stage5-activation-2026-10-15.md)
