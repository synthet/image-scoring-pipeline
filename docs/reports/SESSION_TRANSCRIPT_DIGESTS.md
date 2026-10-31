---
type: Documentation Index
title: Session transcript digests
description: Router for wiki articles distilled from operator-local session exports (secrets and paths stripped). Raw exports stay gitignored; these pages are the public fact layer.
resource: docs/reports/SESSION_TRANSCRIPT_DIGESTS.md
tags: [session, digest, index, transcript]
timestamp: 2026-10-31T00:00:00Z
okf_version: 0.2
status: active
---

# Session transcript digests

Operator-local CLI/Cursor exports may contain pasted secrets — they are **not** in git. When facts are
worth keeping, they are distilled into the pages below (no transcript paths, no credentials).

## Comprehensive month indexes

| Master catalog | Time period | Source scope |
|---|---|---|
| [**SESSION_TRANSCRIPTS_OCTOBER_2026.md**](SESSION_TRANSCRIPTS_OCTOBER_2026.md) | October 2026 | Full provenance inventory and hash catalog for all 37 October root transcripts |

## Thematic session digests

| Digest | Topics |
|--------|--------|
| [SESSION_TRANSCRIPT_DIGEST_2026-07-bird-detect-v0.md](SESSION_TRANSCRIPT_DIGEST_2026-07-bird-detect-v0.md) | Hugging Face `bird-detect-v0` → YOLO crop before BioCLIP |
| [SESSION_TRANSCRIPT_DIGEST_2026-08-cli-judge-labelling.md](SESSION_TRANSCRIPT_DIGEST_2026-08-cli-judge-labelling.md) | CLI judge harness for bird-crop labels + provenance caveat |
| [SESSION_TRANSCRIPT_DIGEST_2026-09-postgres-truncate.md](SESSION_TRANSCRIPT_DIGEST_2026-09-postgres-truncate.md) | `#399` truncate_app_tables rollback |
| [SESSION_TRANSCRIPT_DIGEST_2026-09-gallery-contract-ci.md](SESSION_TRANSCRIPT_DIGEST_2026-09-gallery-contract-ci.md) | Gallery ESLint gate, OpenAPI sync, `ImageEyeKeypoints` type-sync |
| [model-selection-session-2026-10-01.md](model-selection-session-2026-10-01.md) | Initial session summary for label-free model selection and report generation |
| [SESSION_TRANSCRIPT_DIGEST_2026-10-model-selection.md](SESSION_TRANSCRIPT_DIGEST_2026-10-model-selection.md) | Detailed label-free model selection, score analytics, and within-stack divergence |
| [SESSION_TRANSCRIPT_DIGEST_2026-10-localization-stage5-shadow.md](SESSION_TRANSCRIPT_DIGEST_2026-10-localization-stage5-shadow.md) | 4,401-image shadow run, 9p ExifTool timeout retry fix, Stage 5 multi-agent promotion gates |
| [retag-418-session-2026-10-17.md](retag-418-session-2026-10-17.md) | `#418` job 6945 re-tag recovery after host sleep; `jobs/{id}/restart` for failed runs |
| [SESSION_TRANSCRIPT_DIGEST_2026-10-orientation-retag-recovery.md](SESSION_TRANSCRIPT_DIGEST_2026-10-orientation-retag-recovery.md) | RAW portrait thumbnail orientation bug #418, keyword ownership fix #586, retag execution |
| [SESSION_TRANSCRIPT_DIGEST_2026-10-vector-space-separation-and-meta-skills.md](SESSION_TRANSCRIPT_DIGEST_2026-10-vector-space-separation-and-meta-skills.md) | Timing baseline #416, BioCLIP crop vector space collision #641, migration 0042, resume meta-skills |
| [SESSION_TRANSCRIPT_DIGEST_2026-10-localization-gaps-and-focus-evidence.md](SESSION_TRANSCRIPT_DIGEST_2026-10-localization-gaps-and-focus-evidence.md) | Localization rollout gap analysis, 11-frame autofocus study in `docs/af-focus-evidence`, OpenAPI sync |
| [SESSION_TRANSCRIPT_DIGEST_2026-10-runtime-plan-and-phase2-execution.md](SESSION_TRANSCRIPT_DIGEST_2026-10-runtime-plan-and-phase2-execution.md) | Localization runtime plan, 143-image `read_normalized_first` rollback drill, Jev harness repair |
| [SESSION_TRANSCRIPT_DIGEST_2026-10-focus-culling-and-pipeline-integration.md](SESSION_TRANSCRIPT_DIGEST_2026-10-focus-culling-and-pipeline-integration.md) | Eye keypoints as culling tie-breakers, `is_image_bird_species_complete` edge case fix, v9.2.1 release |

Older structured session records (August 2026 research pause) remain under
[RESEARCH_SESSIONS_2026-08-05.md](RESEARCH_SESSIONS_2026-08-05.md).
