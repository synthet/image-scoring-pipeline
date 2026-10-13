---
type: Report
title: Localization agent-panel gates (2026-10-12)
description: Frozen rollout gates, confidence-filtered adjudication, verification and promotion status.
resource: reports/localization-agent-panel-gates-2026-10-12.md
tags: [localization, species, cascade, validation]
timestamp: 2026-10-13T00:07:42Z
okf_version: 0.2
---
# Localization agent-panel gates (2026-10-12)

The cascade gate passes. The small-stratum species gate **fails** its registered
precision requirement: Wilson 95% lower bound **0.8123**, below **0.85**. This
continuation stops before promotion, configuration changes or species refresh.
The small-box geometry gate passed earlier; a usable box does not establish
species accuracy on that crop.

## Scope and evidence

This resumes #592 (selected-region species), #422 (strict floor), #593
(small-stratum rule/4) and #408 (shadow cascade). The earlier frozen comparison
contains 4,401 selected large/medium images. The small candidate manifest contains
274 images; its species sample contains 120 images.

These are **agent-panel labels**, not owner species or box-quality labels.
Owner presence labels remain the independent input to AC-18. No human label was
overwritten. Private crops, manifests, field descriptions and per-image outputs
remain under ignored `.agent/scratch/`; this report publishes aggregate evidence.

The October 11 contract and its amendments remain authoritative. Four judges
were retained, requiring three matching votes. Missing Claude replies did not
reduce the quorum. Frozen reply copies and their SHA-256 receipt are retained in
`.agent/scratch/rollout-20261012-resume/snapshot.json`; the original October 11
artifacts and the 4,401-image comparison remain intact.

## Judge coverage and adjudication

The pilot recorded 19/20 correct for each of Claude, Codex, Antigravity and Cursor.

| Panel | Frames | Claude | Codex | Antigravity | Cursor | Initial consensus | Initial splits |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cascade AC-17 | 164 | 145 | 164 | 164 | 164 | 141 | 23 |
| Small-crop species | 120 | 0 | 120 | 120 | 120 | 89 | 31 |

Claude reached its weekly limit. A separate Codex process supplied species-blind
field-mark descriptions for the 31 small-species splits, without candidates or
votes. Eleven serial calls completed all 31 descriptions; all passed the existing
species/group-word leakage check. Inputs were already stripped blind crops in
isolated batch directories. The describer did not count as an extra vote.

Jev `jev-1.13.0` evaluated one 23-question box batch and two species batches of
20 and 11 questions, using sanitized text only. Acceptance required confidence
at least 0.7. It left all 23 conflicting box judgments unresolved, accepted three
species decisions (confidences 0.72, 0.72 and 0.81), and left 28 species frames
unresolved. The bounded substitution check returned allow at confidence 0.82;
it did not change export authority, quorum or gate thresholds.

## Cascade AC-17 and AC-18

The benchmark uses production YOLO `bird_detect_v1` at 640 and COCO fallback at
0.60, without threshold retry. YOLO detections are adopted unchanged; the cascade
arm additionally includes fallback detections. The two fallback frames consist
of one resolved TIGHT box and one unresolved box.

| Metric | YOLO | Cascade | Registered result |
|---|---:|---:|---|
| TIGHT among resolved bird boxes | 97/140 (69.29%) | 98/141 (69.50%) | AC-17 passes; cascade must be within 5 percentage points of YOLO |
| Independent owner-labelled bird recall | 63/78 (80.77%) | 65/78 (83.33%) | AC-18 recall passes |
| Independent owner-labelled non-bird false positives | 5/71 (7.04%) | 5/71 (7.04%) | AC-18 false positives pass the 10% ceiling |

Box-quality denominators exclude 23 unresolved frames under the contract. The
fallback-only resolved evidence is one frame and must not be interpreted as a
precise fallback-quality estimate. The cascade remains a shadow provider;
passing this gate does not authorize making it the consumer region source.

## Small-crop species gate

The sample retains its registered 60 changed, 40 same, 4 newly labelled,
15 newly abstaining and 1 both-abstaining frames. After confidence filtering,
92 frames are resolved and 28 remain unresolved.

| Criterion | Result | Verdict |
|---|---|---|
| G5a, changed-stratum correct labels | New 36 versus old 6 | Pass |
| G5b, cohort-weighted correct labels | New 206.0 versus old 151.5 | Pass |
| G5b, cohort-weighted wrong labels | New 24.0 versus old 117.5 | Pass |
| G5c, weighted accepted-label precision | 0.8958; Wilson 95% interval 0.8123-0.9447; effective n 84 | **Fail**, lower bound below 0.85 |

Weights use resolved samples within each outcome stratum, following the existing
gate implementation. No sample was enlarged after viewing results. The initial
pre-adjudication lower bound was 0.8325; that artifact is preserved separately.
Unresolved exclusions and agent-derived labels limit what these estimates prove.

Earlier evidence remains separate: the 4,401-image selected-region species gate
recorded a lower bound of 0.8859 and a 200/200 parity check; rule/4 geometry
recorded 128/128 resolved usable boxes from 130 fresh frames, with two unresolved
and lower bound 0.9709. Those results do not override this small-species failure.

## Implementation and verification

Branch `feat/592-stage5-agent-panel-gate` was pushed through `c285c20` and verified
against origin. Its four implementation commits contain the ExifTool retry,
selection-based species routing and strict floor, judge harnesses, and pending
shadow cascade persistence/small-species sampling support. Default enablement
remains gated. Local `master` was not merged or production-deployed here.

Fresh verification before the implementation commit:

```text
docker exec -w /app -e PYTHONPATH=/app image-scoring-gpu-shell timeout 180 python -m pytest tests/test_localization_cascade_runner.py tests/test_localization_cascade.py tests/test_judge_panels.py tests/test_bird_species_regions.py tests/test_thumbnails_exiftool_retry.py -q
```

Result: **38 passed**. Scoped ruff on the four pending files and staged whitespace
checks passed. An initial command referenced nonexistent
`tests/test_localization_runner.py`, collected no tests, and was corrected; it is
not counted as passing evidence. No full suite or production inference was run.

## Operational state and next action

The read-only MCP check confirmed portrait job **6945 paused**. PostgreSQL and
GPU-shell were running; no WebUI container was running. GPU-shell was restarted
only for local gate computation. No production job was submitted, no selection
was promoted, no keyword/species refresh ran, and no rollout flag was changed.
Unrelated release, species-list research and agent-setup edits were preserved.

Stop promotion on the failed small-species gate. The specific small-species
amendment permits considering geometry-only promotion **with small selections
excluded from region species**, but that exclusion is not implemented or deployed
by this continuation. Record that decision and its consumer behavior before any
such write. Otherwise retain the current selections and gather independently
reviewed evidence under a new preregistered evaluation; do not lower this gate.

Passing large/medium species and shadow cascade work still needs scoped delivery,
a fresh frozen-state/keyword-preservation preflight, and a verified database
backup before any production write. Keep WebUI stopped and job 6945 paused.

See [the rollout status](../architecture/pipeline/localization-rollout.md),
[the frozen comparison](localization-species-policy-validation-2026-10-10.md), and
[the October 10 work log](localization-session-work-log-2026-10-10.md).
