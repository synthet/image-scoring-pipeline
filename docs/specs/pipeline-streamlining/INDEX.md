---
type: Documentation Index
title: Pipeline streamlining — spec hub
description: Implementation specs, roadmap, dependencies and shared conventions for the streamlined pipeline with subject-aware scoring (#406–#413).
resource: docs/specs/pipeline-streamlining/INDEX.md
tags: [specs, pipeline, localization, scoring, detection, roadmap]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
status: proposed
---

# Pipeline streamlining — spec hub

This hub holds the implementation specs for the target order described in
[planning/pipeline-streamlining.md](../../planning/pipeline-streamlining.md):

import → rendition → embeddings + scene route → localize → species on crop → subject-aware scoring
(captions and keywords alongside) → group bursts → pick / keep / reject.

Each spec follows the repo's `/spec` and `/plan` format. Acceptance criteria are EARS sentences
numbered `AC-n`, which the `validate-implementation` skill verifies later.

## Specs

| # | Spec | Issue | Kind | Depends on |
|---|---|---|---|---|
| 01 | [Decode-once rendition](01-rendition.md) | #406 | refactor | — |
| 02 | [Phase graph changes](02-phase-graph.md) | #407 | refactor | — |
| 03 | [Detector cascade](03-detector-cascade.md) | #408 | feature (shadow) | 01 (soft) |
| 04 | [Subject-aware scoring](04-subject-aware-scoring.md) | #409 | feature | 01, 02, 03, labelled bursts |
| 05 | [Scene route](05-scene-route.md) | #412 | research → feature | 01 (soft) |
| 06 | [Species beyond birds](06-multi-taxon-species.md) | #413 | research → feature | 03, 05 |
| 07 | [Blockers, decisions and suggestions](07-blockers-and-decisions.md) | #417 | register | — |

## Dependencies

```mermaid
flowchart LR
    M0["M0: close rollout stage 4<br/>legacy import, test-DB fix"]
    R["01 rendition #406"]
    G["02 phase graph #407"]
    C["03 cascade #408"]
    S5["rollout stage 5<br/>BioCLIP on regions"]
    SR["05 scene route #412"]
    SP["06 species #413"]
    L["labelled bursts<br/>~300, human"]
    Q["04 subject-aware scoring #409"]

    M0 --> C
    R --> C
    R --> Q
    G --> Q
    C --> Q
    C --> S5
    SR --> SP
    S5 --> SP
    L --> Q
```

## Roadmap

**Current status (2026-10-12):** #594 merged cascade persistence, the active-selection
species reader and gate evidence. Cascade AC-17/AC-18 pass; small-crop species
fails (0.8123 < 0.85). Live activation/refresh is pending. Use
[the current handoff](../../../NEXT_STEPS.md) for the execution order and
[the gate report](../../reports/localization-agent-panel-gates-2026-10-12.md)
for evidence. The roadmap is not a command to repeat completed imports.

| Milestone | Contents | Exit |
|---|---|---|
| **M0 — unblock** | Decisions and legacy import completed; truncate fix delivered (#427). Lane admission/completion observed; registration boundary fixed (#585). | Production retry timing remains unobserved; complete those observations under the rollout policy. |
| **M1 — foundations** | 01 rendition, 02 phase graph. | Every AC in both specs passes. Existing runs select the same work, except that keywords no longer waits for scoring. |
| **M2 — detection** | Cascade persistence and AC-17/AC-18 evidence merged in #594; scene route implemented (#412). | Verify deployed wiring, enable/observe the cascade in shadow; consumer-source adoption remains separate. |
| **M3 — consumers** | Region species reads active production selections; existing-cohort gate/parity pass. Small-crop species fails; multi-taxon work remains. | Complete approved-cohort activation/refresh and the small-selection exclusion/evidence requirement. BioCLIP does not automatically consume current cascade runs. |
| **M4 — subject-aware scoring** | 04 in shadow, the crop-only backfill, then promotion. | Fusion v2 beats v1 on the labelled bursts, and the operator approves the rating change. |

**Parallel track: labelled bursts.** About 300 bursts of human pick/reject labels, stratified by
subject-size tercile. This is step 0 of
[subject-aware-culling-evidence.md](../../planning/subject-aware-culling-evidence.md), and it is
the only way to pass M4's gate honestly. Tracked in #415. No usable human labels exist today
([07 §4.4](07-blockers-and-decisions.md#44-labelled-bursts-existing-labels-then-collection)).
Those September counts are historical; reconcile current owner-label coverage
before collection. Agent species/box labels from #594 do not satisfy #415.

**Parallel track: evidence and explainability.** These tracks sit beside M0–M4. They reuse the same
regions, rendition and labels, but none of them changes production scores.

| Milestone | Contents | Needs | Exit |
|---|---|---|---|
| **E1: bursts** | Sub-second continuous-burst segmentation inside stacks (#424) | M1 (spec 02 split) | The threshold is chosen from data, and the sub-burst id is exposed to the gallery. |
| **E2: evidence v0** | Named per-criterion bands from the primary region, in research JSONL (#423) | M0 (legacy import), E1 | A per-criterion within-burst AUC table, and a keep/drop decision per criterion. |
| **E3: subject artifacts** | Keypoint and mask providers (#426); primary-region policy (proposal on #408) | M2 | Visibility calibration and mask-vs-box-grade benchmark. |
| **E4: explainability** | Sub-scores, bands and reasons through the API (spec 04 O-4); gallery breakdown, nearly-tied badge and overlays | E2, #415 | The display gate passes per criterion (CI above chance on labelled bursts). |

The consolidated stage-by-stage status, including these tracks, is at the top of the
[localization rollout](../../architecture/pipeline/localization-rollout.md).

## Shared conventions

Every spec follows these rules. They carry over from the
[localization rollout invariants](../../architecture/pipeline/localization-rollout.md#rollout-invariants).

- **Fail open.** A missing, failed or stale upstream artifact never blocks core inference; the
  consumer falls back to full frame.
- **Versioned artifacts.** Every new artifact records the source/rendition identity, the model or
  detector version, and the config hash. Flags are controls, not provenance.
- **Shadow before authority.** New outputs land in shadow, isolated from production predicates, and
  are promoted by a flag change only after their gate passes.
- **No invented contracts.** Every config key below is **new**. Each must be added to
  `config.example.json` and [CANONICAL_SOURCES.md](../../CANONICAL_SOURCES.md) in the PR that
  introduces it. A new `phase_code` or API field follows
  [cross_repo_contract_change.md](../../../.agent/workflows/cross_repo_contract_change.md).
- **Measured claims only.** Each benchmark reports its cohort, labels, confidence intervals and
  limits, the way #377 does.

## Configuration keys from the design

The table preserves the original design; several keys now have implementations.
Check `config.example.json` and current code rather than adding duplicate keys.
Cascade persistence uses the merged `localization.cascade` flag. Proposed keys
do not authorize production activation.

| Key | Default | Spec |
|---|---|---|
| `rendition.enabled` | `false` | 01 |
| `rendition.long_edge` | `2048` | 01 |
| `rendition.cache_max_gb` | `50` | 01 |
| `rendition.scoring_source` | `false` | 01 |
| `pipeline.culling_requires_scoring` | `true` | 02 |
| `localization.detectors.coco.enabled` | `false` | 03 |
| `localization.cascade.enabled` | `false` | 03 |
| `localization.cascade.refine_area_frac` | `0.02` | 03 |
| `scoring.subject.enabled` | `false` | 04 |
| `scoring.subject.crop_policy` | `score_subject_v1` | 04 |
| `scoring.fusion_version` | `v1` | 04 |
| `scene_route.enabled` | `false` | 05 |
| `scene_route.skip_detection_min_prob` | `0.9` | 05 |
| `species.taxa` | `["aves"]` | 06 |

## Related

- [planning/pipeline-streamlining.md](../../planning/pipeline-streamlining.md) — the plan these specs implement
- [architecture/pipeline/localization-rollout.md](../../architecture/pipeline/localization-rollout.md) — the rollout they build on
- [planning/localization-stage4-slice1-status.md](../../planning/localization-stage4-slice1-status.md) — M0 work items
- [planning/models/ONNX_CONVERSION_FEASIBILITY.md](../../planning/models/ONNX_CONVERSION_FEASIBILITY.md) — ONNX runtime, which spec 03 needs
