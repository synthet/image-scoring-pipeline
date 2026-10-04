---
type: Report
title: Session digest — CLI agents as bird-crop labelling judges (2026-08)
description: Design facts from image-scoring-skills session exports on using external CLI agents as judges for the bird-crop labelling runbook, including provenance and ground-truth caveats.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-08-cli-judge-labelling.md
tags: [session, digest, labelling, multi-agent, bird-crop, skills]
timestamp: 2026-09-27T16:55:00Z
okf_version: 0.2
---

# Session digest — CLI agents as labelling judges (2026-08)

Source: **image-scoring-skills** session exports, cross-read against
[guides/BIRD_CROP_LABELLING.md](../guides/BIRD_CROP_LABELLING.md) and
[SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md](SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md).

## Intent

Experiment with **multiple CLI agents** (`claude -p`, `codex exec`, `agy`, in-editor Cursor leg) as
**judges** for the bird-crop labelling instructions, instead of only human sheet filling.

## Operator choices recorded in session

| Question | Choice |
|----------|--------|
| Where verdicts land | Write **`label_set.csv`** directly (not a separate human-only column) |
| Judges | Claude, Codex, Agy, Cursor (orchestrator reads sheets when no Cursor CLI on PATH) |
| Deliverable | Skill + slash command + PowerShell harness under skills repo |

## Ground-truth caveat (explicit in session)

The bird-crop study runbook defines **human** `verdict` as the non-circular label source. If judges
write `label_set.csv`, that column becomes **model-derived**. Any harness must stamp **provenance**
(judge list, model ids, `judge-derived` flag) in a **sidecar JSON** so downstream reports state what the
labels actually are — consistent with the UUID sidecar policy in the August close-out record.

## Related

- [BIRD_CROP_LABELLING.md](../guides/BIRD_CROP_LABELLING.md) — human labelling runbook
- [RESEARCH_SESSIONS_2026-08-05.md](RESEARCH_SESSIONS_2026-08-05.md) — concurrent research hub
