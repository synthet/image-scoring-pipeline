---
type: Report
title: Localization rollout session work log and summary (2026-10-10)
description: Completed shadow comparison, mounted-source ExifTool diagnosis, verification evidence and Docker shutdown handoff.
resource: reports/localization-session-work-log-2026-10-10.md
tags: [localization, session, work-log]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
---
# Localization rollout session work log and summary (2026-10-10)

The continuation completed the frozen 369-species / 0.5 shadow comparison for
**4,401 distinct expected images with zero final skips**. It did not promote
Stage 5. The [validation report](localization-species-policy-validation-2026-10-10.md)
contains the full aggregate evidence; [NEXT_STEPS.md](../../NEXT_STEPS.md) is the
current operational handoff.

The later continuation reproduced the ExifTool timeout at the mounted 9p
filesystem boundary. At the user's request, both running containers were then
stopped and Docker Desktop shut down. Portrait job 6945 remains paused.

## Summary

| Outcome against frozen stored labels | Images |
|---|---:|
| Same accepted label | 2,961 |
| Changed accepted label | 753 |
| Newly labelled | 234 |
| Now abstains | 403 |
| Both abstain | 50 |
| Total | 4,401 |

These measure agreement with stored labels, not labelled accuracy. The run used
the committed 369-name list and cached BioCLIP 2 revision; unrelated species-list
research in the working tree was excluded. Small regions stayed in shadow.

## Work log

1. Read the paused handoff and rollout documentation, inspected the dirty working
   tree, and resumed the frozen selected-region comparison. Portrait/release
   work was kept separate.
2. Restored Docker Desktop and the existing PostgreSQL/GPU-shell containers.
   WebUI remained stopped. Verified frozen sources, geometry, identities,
   stored labels, inference code and cached model before inference.
3. Completed partition 0 by retaining its 2,200 successes and retrying only its
   missing image, yielding 2,201 results. Preserved original attempts/checkpoints.
4. Partition 1 repeatedly encountered mounted-source ExifTool extraction
   timeouts at the existing ten-second boundary. Instrumented recovery retained
   checkpoints of 487, 532 and 540 successes; source-cache warming did not resolve
   the failures. The underlying cause remains unproven.
5. Probed byte-identical local staging. Two retained controls reproduced decode
   route, dimensions, crop-pixel hashes and top-three rankings/probabilities
   exactly. The latest failed source classified successfully from identical
   local bytes; duplicate controls were excluded from final coverage.
6. Continued only missing IDs, retaining earlier successes. Overlapped local
   copying with single-model inference using one I/O thread, at most two temporary
   copies and a 128MiB bound. Partition 1 completed all 2,200 results.
7. Merged both partitions after a fresh read-only preflight. Verified exact
   expected-ID coverage, no duplicates/skips, preserved checkpoint results,
   frozen code/model/preprocessing, all decode/crop provenance and 1,660
   source/staged hash bindings. Owned temporary copies were removed.
8. Saved the aggregate report, refreshed rollout status and indexes, appended
   documentation log entries, and replaced the paused root handoff with completed
   results and next gates. Historical handoffs and partial audits were retained.

## Verification and operational state

- Final comparison: 4,401/4,401 distinct expected results; zero final skips.
- Decode routes: 4,399 RAW previews and 2 direct decodes.
- Targeted OKF documentation lint: zero errors and warnings. `git diff --check`
  passed; Git emitted existing line-ending conversion notices.
- Final read-only database check: portrait job **6945 paused**, zero running jobs.
  No localization-policy worker remained.
- No production job was submitted or resumed. Keywords, scores, selections,
  phase status, rollout flags and original photos were unchanged.
- Production decoding and its timeout were unchanged. Local staging was a
  workaround for this shadow comparison.
- No commit or push occurred. Existing unrelated edits remain preserved.

## Retained artifacts and next work

**Superseded next actions:** the work log below preserves October 10 evidence.
The [October 12 gate report](localization-agent-panel-gates-2026-10-12.md) and
[current handoff](../../NEXT_STEPS.md) supersede its unfinished code/validation
steps: #594 is merged; small-crop species failed its gate; activation remains.

Per-image results and personal photo paths remain under ignored `.agent/scratch/`.
The final `localization-policy-20261010-full.json/.md`, complete partitions,
staging probe, postflight, bounded-run contract and intermediate checkpoints
provide recovery and provenance evidence. Do not rerun over completed artifacts.

Review labelled or second-folder evidence and #422 policy follow-ups before
Stage 5 promotion. Production retry timing remains unobserved; mounted-source
ExifTool latency needs separate diagnosis. Portrait job 6945, keyword/species
restoration, #418 closure and release 9.0.0 remain separate work. Stage 6 still
waits on labelled bursts (#415), storage/fusion (#409) and evidence (#423).

See the [rollout status](../architecture/pipeline/localization-rollout.md) and
[wider handoff](localization-rollout-next-steps-2026-10-09.md).

## Mounted-source timeout diagnosis and shutdown continuation

The user prioritized ExifTool diagnosis, then requested pausing processing and
shutting down Docker Desktop. This continuation used CPU-only extraction with
no BioCLIP model loaded and no production job submission.

- Tested frozen images 36529, 46372 and 46614 with the unchanged command
  `exiftool -b -JpgFromRaw` and ten-second timeout. Alternated mounted inputs
  and SHA-256-identical local copies; verified frozen source size/mtime before
  and after, and source hashes after testing. Used one local copy at a time.
- First probe: 21 extractions, three timeouts. Image 46372 timed out on all
  three mounted repetitions at 10.104–10.139 seconds, returning zero output.
  Its identical local copy succeeded three times in 0.402–0.525 seconds.
  All nine local extractions across the three images succeeded.
- Process startup took at most 1.735ms. During the three timeouts, 144 of 153
  sampled child wait states were `p9_client_rpc`, with disk-sleep state and
  continuing read counters. Source mount type was `9p`; local staging used
  the container's `overlay` filesystem. This identifies filesystem access as
  the observed failing layer; the underlying host-side cause is still unknown.
- Second probe: five successful extractions of 46372. Mounted calls took
  0.443–2.352 seconds; local calls took 0.174–0.197 seconds. Eleven samples
  identified `read` on the actual input descriptor, including 8KiB reads
  waiting in `p9_client_rpc`. This probe confirms the access path while showing
  the slowdown is intermittent; it did not reproduce a timeout.
- Successful JPEG bytes and decoded pixel hashes matched within each image
  across both filesystem modes. Production decoder hashes were unchanged.
  Owned temporary copies were removed. Completed comparison artifacts were
  neither rerun nor overwritten.
- Code inspection found that a `JpgFromRaw` timeout skips `PreviewImage`,
  because both calls share one exception handler. `dcraw` and `magick` are
  absent in this GPU shell. Installed rawpy 0.26.1 accepts the existing
  `user_sat=None` parameter; its sensor fallback was not exercised here.

Retained private evidence: `.agent/scratch/exiftool-timeout-diagnosis-20261010T225631Z/`
and `exiftool-timeout-diagnosis-20261010T225806Z/` contain separate result/checkpoint
files. The diagnostic and summary scripts remain in ignored scratch. These
measure extraction latency, not Stage 4 production retry/backoff.

Next diagnosis should trace host-side 9p/storage delays during a slow extraction.
A production mitigation should be evaluated separately, preserving decode-route,
orientation and pixel identity; no timeout increase or staging change was deployed.

Final read-only SQL found job **6945 paused** and **zero running jobs**. Stopped
`image-scoring-gpu-shell` and `image-scoring-postgres`; `docker ps` returned no
running containers before `docker desktop stop --timeout 60` completed. Neither
Docker Desktop nor its backend process remained. The subsequent Desktop status
query reported that Desktop was not running. No further processing was started.

Tracked documentation whitespace checks passed. Targeted OKF lint could not run
on the available host Python because PyYAML is missing; Docker remained stopped.
