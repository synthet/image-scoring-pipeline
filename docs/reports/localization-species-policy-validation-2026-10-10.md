---
type: Report
title: Localization species policy validation (2026-10-10)
description: Complete frozen 369-species/0.5 comparison on 4,401 selected images, zero final skips, verified input provenance and unchanged production state.
resource: reports/localization-species-policy-validation-2026-10-10.md
tags: [localization, species, rollout, validation]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
---

# Localization species policy validation (2026-10-10)

The frozen **369-species / 0.5** shadow comparison completed for all **4,401**
selected images, with **zero final skips** and exactly one final result per expected
ID. Both partitions passed (2,201 and 2,200). Final preflight and merge verified
unchanged source metadata, cohort geometry, selected identities, stored baseline,
classifier, canonical comparison, decoder, cropper and cached model revision.

This is agreement evidence against stored species labels. Labelled accuracy,
keyword rewrites and Stage 5 promotion remain separate gates.

**Later status:** [the October 12 agent-panel gates](localization-agent-panel-gates-2026-10-12.md)
passed on this existing cohort, with 200/200 production-path parity; the separate
small-crop species gate failed. PR #594 merged the code and evidence, while live
activation and keyword refresh remain pending in [the current handoff](../../NEXT_STEPS.md).
The frozen comparison and policy described below remain historical evidence.

## Full-cohort outcomes

| Outcome against the frozen stored baseline | Images |
|---|---:|
| Same accepted label | 2,961 |
| Changed accepted label | 753 |
| Newly labelled | 234 |
| Now abstains | 403 |
| Both abstain | 50 |
| Total classified | 4,401 |
| Final skips | 0 |

Of the images labelled both times, 20.27% changed top-1; 241 selected another
species already present among their stored labels. Among 1,480 unchanged labels
with actual stored model probabilities, mean confidence delta was +0.0362,
median +0.0036, and confidence rose on 971. These are model-confidence and
agreement measurements, not accuracy improvements.

## Frozen scope

The cohort is the exact 4,401 promoted large/medium selections under
`v1_regate_rule/3:a1c2e1f64b24cc79`. Small regions remain in shadow.
The candidate file is the committed 369-name list from
`6854efcce1e5a447976738392888ccb927866c6c`; dirty species-list research was excluded.
Candidate-list JSON SHA-256:
`dc6984a9fa305db099f7a155d1e319fdf495c0917897c2738d2c5eee79674070`.

BioCLIP 2 used cached revision `2957b322090f9cb17ae72c71981c7218a28d81e0`,
with `open_clip_model.safetensors` and crop padding 0.1. Both partitions used
identical preprocessing. The canonical comparison accepts confidence **at least
0.5**. No prediction equalled 0.5, so a strict-above rule would produce the same
outcomes on this cohort; the policy follow-up remains separate.

Ten primary stored labels from the October 8 report were absent before the
October 9 snapshot. The current report uses that frozen current baseline. The
historical 360-species predictions do not isolate a candidate-list effect: an
excluded earlier pilot had an unexplained RAW ranking discrepancy. The
recovered-runtime 20-image pilot reproduced the retained rankings/probabilities.
Report the current agreement outcomes independently of that historical control.

## Recovery and input provenance

Early mounted-source inference encountered RAW extraction failures. Partition 0
retained 2,200 successes and recovered only its one missing image. Partition 1
retained successive checkpoints of 487, 532 and 540 successes. Instrumentation
observed ExifTool `-JpgFromRaw` exceeding the existing ten-second timeout at
10.047 and 10.108 seconds. Full source-cache warming did not resolve that boundary.
The underlying reason for the slow calls remains unproven.

An independent exact-byte local-staging probe reproduced two retained controls
exactly: decode route, decoded/crop sizes, crop-pixel hashes and top-three species
names/probabilities. The latest failed RAW classified from its identical local
copy in 1.31 seconds. Source/copy SHA-256 equality was required before inference.

The continuation retained every earlier successful result. It staged each missing
input on the container's local temporary filesystem, preserving the source suffix
and all bytes, then invoked unchanged canonical inference. One new probe result
was retained; duplicate controls were excluded from final coverage. Source copying
was later overlapped with inference using one I/O thread and one GPU model process,
with at most two owned copies below a 128MiB footprint bound. Each completed copy
was removed from the owned directory; final merge verified no temporary copies remained.

Exactly **1,660** final predictions have source/staged-byte hash bindings. Every
one of the 4,401 results has decode and crop-pixel provenance: **4,399 raw_preview**
and **2 direct**. Final merge verified both policies, model revision and
preprocessing, all expected distinct IDs, exact preservation of earlier successful
checkpoint rows, partition report hashes, probe equivalence, and frozen live state.
The intermediate 2,741-result partial audit remains historical evidence; the full
report supersedes its incomplete coverage status.

Private artifacts remain under ignored `.agent/scratch/`:

- `localization-policy-20261010-full.json/.md`: complete final results and aggregate summary.
- `localization-policy-20261010-part-0-recovered.json` and `localization-policy-20261010-part-1-staged-prefetch.json`: verified complete partitions.
- `localization-policy-20261010-staging-probe.json` and `localization-policy-20261010-postflight.json`: exact-control and final frozen-state checks.
- `localization-policy-20261009-*` and the retained October 10 checkpoints: immutable inputs, initial attempts and recovery history.

Personal photo paths and per-image results stay local. Runtime includes recovery,
staging and prior attempts; it is not the dedicated #416 GPU timing baseline.

## Rollout state and next gates

Only the existing PostgreSQL and GPU-shell containers were restored. WebUI stayed
stopped, and portrait job 6945 was not resumed. No keywords, scores, selections,
phase state, rollout flags or original photos were written. The production decoder
and its timeout were not changed; local byte staging unblocked this shadow comparison.

The normal-indexing boundary fix (#585, migration 0041) is already merged and
deployed. The October 9 automatic lane observation remains historical evidence
after staged-data cleanup; production retry timing remains unobserved.

Review these agreement results alongside labelled or second-folder validation
before Stage 5 promotion. Keep region reads and crop scoring at their existing
settings. Strict-threshold, scene-routed non-bird and range-list follow-ups remain
on #422; labelled bursts and Stage 6 storage/fusion remain separate work.
Investigate the production mounted-source/ExifTool latency independently.
Portrait job 6945, its keyword/species restoration, #418 closure and release 9.0.0
remain separate from this read-only comparison.

See the [rollout](../architecture/pipeline/localization-rollout.md),
[historical live report](localization-stage4-live-nef-2026-10-09.md) and
[wider handoff](localization-rollout-next-steps-2026-10-09.md).
