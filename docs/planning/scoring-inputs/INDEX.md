---
type: Documentation Index
title: Scoring orientation and model-input task index
description: Issue-linked tasks for scoring orientation, model input routing and preprocessing evaluation.
resource: planning/scoring-inputs/INDEX.md
tags: [planning, scoring, orientation]
timestamp: 2026-10-06T04:44:10Z
okf_version: 0.2
---
# Scoring orientation and model-input tasks

Planning snapshot for the orientation investigation. GitHub issues and the [Project board](https://github.com/users/synthet/projects/1) remain the canonical queue; these files are implementation handoffs, not a second backlog.

## Contract and clarification

Camera orientation means EXIF rotation/reflection followed by upright width and height. It is independent of a semantic portrait scene or subject-facing direction. Apply orientation exactly once before any scoring resize/crop/pad. Display and localization evidence must agree on the oriented coordinate frame; retain our rendition descriptors and existing coordinate contracts.

Keep source EXIF/storage dimensions, upright rendition dimensions and padded model-canvas dimensions distinct. A native portrait image can have EXIF orientation 1. Uniform scaling preserves aspect ratio; crop/pad mappings must use the declared oriented frame. Supporting both portrait and landscape does not imply identical model scores after a physical image rotation.

Initial correctness work retains current padding, input size defaults and decoder preference. Per-model routing is a separate fix. Shared-cache adoption and alternative resize policies require measured acceptance; the reference application's preview sizes are not configuration defaults for our models.

## Task files

Start with the [next-steps resume plan](NEXT-STEPS.md), which records the published display/export fixes and the remaining implementation order. The session resumed on 2026-10-06; orientation/routing fixes and focused verification are locally implemented, with policy evaluation and gallery compatibility tracked separately.

| Task | Scope |
|---|---|
| [01-scoring-orientation](01-scoring-orientation.md) | P1: upright quality-scoring pixels, versioned cache and targeted rerun |
| [02-model-input-routing](02-model-input-routing.md) | P1: actual per-model input selection for local/remote inference |
| [03-preprocessing-evaluation](03-preprocessing-evaluation.md) | P2: evidence for model-native resizing and shared-rendition scoring adoption |
| [04-gallery-orientation-verification](04-gallery-orientation-verification.md) | Existing gallery #176: tagged/baked previews and overlay compatibility |
| [VERIFICATION](VERIFICATION.md) | Tests, real-model measurements, provenance and bounded rollout |
| [RESEARCH-REVIEW](RESEARCH-REVIEW.md) | Research corrections, checkpoint constraints and preprocessing gates |
| [BENCHMARK-RESULTS](BENCHMARK-RESULTS.md) | Five-model labeled comparison, sampling limitations and per-model HOLD decisions |

## Filed issues and board status

- [Backend #568](https://github.com/synthet/image-scoring-pipeline/issues/568): scoring orientation.
- [Backend #569](https://github.com/synthet/image-scoring-pipeline/issues/569): per-model input routing; depends on #568.
- [Backend #570](https://github.com/synthet/image-scoring-pipeline/issues/570): policy evaluation; depends on #568 and #569.
- [Gallery #176 checklist](https://github.com/synthet/image-scoring-gallery/issues/176#issuecomment-6009529793): orientation/overlay compatibility; existing issue retained.

Backend #568, #569 and #570 were claimed through the repository stage harness for the resumed work. All remain open on [Project 1](https://github.com/users/synthet/projects/1), Stage=Claimed until the first commit. Existing `stage:backlog` labels are not the canonical Project Stage. No commit, push or deployment has been performed. The existing gallery checklist was reconciled with published display/export evidence.

## Dependency order and coverage

1. Orientation correction (OR-AC-1..7); gallery checks (GA-AC-1..4) can develop in parallel and finish on the corrected samples.
2. Per-model routing (RT-AC-1..5), based on the upright-source contract.
3. Policy evaluation (EV-AC-1..6), after both correctness baselines are available.

Each task maps acceptance criteria to ordered test/implementation steps and a rollout/rollback gate. Backend tests and real inference run in gpu-shell. Gallery verification runs in its repository. Current worktree thumbnail changes are existing work and must be inspected/preserved when implementation begins. Checked acceptance items now cite local implementation evidence; unchecked items remain pending.

## Related existing ownership

- [Backend #406](https://github.com/synthet/image-scoring-pipeline/issues/406): shared decode/rendition architecture and baked thumbnails.
- [Backend #418](https://github.com/synthet/image-scoring-pipeline/issues/418): thumbnail-based ML consumers and embedding impact.
- [Backend #320](https://github.com/synthet/image-scoring-pipeline/issues/320): canonical model-input documentation.
- [Gallery #176](https://github.com/synthet/image-scoring-gallery/issues/176): thumbnail compatibility plus separate score input-mode readers.

Duplicate search covered both repositories. The new tasks isolate quality-scoring correctness and evaluation; shared decoding, thumbnail-consumer migration and gallery compatibility retain their existing issue owners.

## Provenance

Behavioral context: derived from competitive analysis of a commercial application's observable behaviour and documentation; contains no code, identifiers, fitted constants or model artefacts from it. Implementation evidence and proposed changes below are from this repository and the gallery repository. Reference preview dimensions and encoding settings are not adopted as requirements.
