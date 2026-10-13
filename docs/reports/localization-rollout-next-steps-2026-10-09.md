---
type: Report
title: Localization rollout next steps (2026-10-09)
description: Status after the October 1–9 localization transcripts. Production fixes through PR #590 are merged; portrait re-score job 6945 is paused and the stack is stopped; release 9.0.0 is local only.
resource: reports/localization-rollout-next-steps-2026-10-09.md
tags: [localization, rollout, operations, status]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
sources:
  - id: transcripts
    resource: 2026-10-01 through 2026-10-09 session exports at the repo root
    title: Claude Code session transcripts
  - id: tree
    resource: git status and docker ps on 2026-10-09
    title: Working tree and container check
---

# Localization rollout next steps (2026-10-09)

> **Historical handoff.** Its stopped-stack and unimplemented-gate instructions
> describe October 9. Continue from [the current handoff](../../NEXT_STEPS.md)
> and [the October 12 gates](localization-agent-panel-gates-2026-10-12.md): #594 is
> merged, cascade gates pass, and small-crop species fails. This page does not
> authorize restarting WebUI or resuming 6945 as part of the localization task.

Localization fixes are merged and the stack is stopped. Portrait re-score job **6945** is paused at 2,059 of 2,324 images, and release **9.0.0** exists only as uncommitted local files.

Nine transcripts from October 1–9 are one localization thread plus a GPU-runner side thread. Checked after the last transcript: `master` is `1840726` (merge of PR #590), `CHANGELOG.md` and `modules/version.py` are dirty at `9.0.0`, and `image-scoring-webui`, `image-scoring-gpu-shell`, and `image-scoring-postgres` are stopped. The job count is from the transcript; Postgres was already down, so it was not re-queried.

## Done

- Code and production deploy through #590: upright ML inputs (#418), species floor (#422), `registered_at` / migration 0041 (#584), path crash (#587), tagging `overwrite` (#589), remote scoring host TOPIQ/ARNIQA (#588). A single-image scoring smoke test passed (image 663).
- #418 re-embed verified: stored CLIP vectors match upright pixels (cosine 1.00) on the 80-image check.
- Stage 4 live lane was observed (jobs 6939 and 6941). See [Stage 4 live Nikon NEF lane observation](localization-stage4-live-nef-2026-10-09.md). Scratch NEFs 245328–245343 and their folders were removed from the database afterward, and the NEF/XMP copies under `.agent/scratch/localization-stage4-*` were deleted. The image IDs cited in that report no longer exist. The lane’s “new images” count is 0.
- Selected-region keypoints and the species comparison are recorded complete in the [October 8 continuation](localization-rollout-continuation-2026-10-08.md) (4,401 images). The October 9 session asked to confirm that and did not re-check it.

## In progress

- Job 6945 (2,324 portrait images) is paused in the database at 2,059/2,324 in scoring. Keywords and captions have not started.
- Release 9.0.0 is written in `CHANGELOG.md` and `modules/version.py`, not committed or pushed.

## Not started

- After 6945: verify scores, keywords, and captions, including the 47 images job 6943 left with scoring failed. Re-run `bird_species` to put species keywords back, then close #418.
- #422 follow-ups: abstain only when confidence is strictly above 0.5, skip species on scene-routed non-birds, and use a range-aware species list.
- #586: a keyword re-run still deletes species and hand-added keywords. A full rewrite was accepted for this portrait batch.

## Blocked

- Stage 4 retry timing. No retryable failures have occurred in production. Unblocked by a real failure, or by accepting the isolated-test evidence.
- Vision judges for #408. The orchestrator Codex/Antigravity image path is broken in the separate `subagent-orchestrator` repo.
- #415 (about 300 labelled bursts) and #416 (GPU timing baseline). #415 was confirmed at 0 usable labels.

## Needs a decision

- Resume 6945 now, or leave the stack down.
- Commit and push 9.0.0 now, or after 6945 finishes.
- Stage 4 retry gate: accept the isolated test, or wait for a live failure.

## Unfinished business

- Uncommitted work from other sessions, left out of 9.0.0: `data/bird_species_list.txt`, the Austin frequency CSV, `data/other_animal_species_list.txt`, `scripts/research/clip_species_study.py` and its test, `docs/technical/BIRD_SPECIES_WALKTHROUGH.md`, `.claude/HOOKS.md`, `.claude/settings.json`, and `.gitignore`.
- Keep `.agent/scratch/418/` (keyword and vector backups) until #418 is closed. `422/` and `stage5-nef/` are still there. Database backup: `backups/postgres/images_before_0041_20261009_101626.dump`.
- A git-ignored curl allow rule in `.claude/settings.local.json` permits `POST http://localhost:7860/api/*`.
- The October 4 GPU load-balancer session stopped at a usage limit inside worktree `isb-wt-549`. Remote GPU fallback (#529) and transport v2 later merged. That plan itself was not finished in the transcript.
- Heal-thumbnails run 6839 was stuck with no steps. That session never reported a fix.

## Next step

Bring the stack up and resume job 6945:

```text
docker compose --profile gpu-shell up -d db webui gpu-shell
```

Then `POST /api/workflow-runs/6945/resume` with a reason body. Keywords, the species restore, and closing #418 wait on the remaining 265 scoring images.
