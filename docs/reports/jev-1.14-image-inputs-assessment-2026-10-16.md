---
type: Report
title: Jev 1.14 image inputs assessment
description: Whether Jev 1.14 image inputs can serve the localization and species gates, which claims were verified, and the conditions before use.
resource: reports/jev-1.14-image-inputs-assessment-2026-10-16.md
tags: [jev, typesafe, species, validation, security]
timestamp: 2026-10-16T00:00:00Z
okf_version: 0.2
---

# Jev 1.14 image inputs assessment

A third-party deep-research report claimed that Jev 1.14, released on 2026-10-14, accepts images. This note checks the
claims that matter to us and records whether we can use the feature.

**Conclusion:** use it for research and gate judging only, after the conditions below. Do not put it in the
production pipeline yet. Until those conditions are met, the harness rule that Jev `state` holds no images still
applies; see [the Jev agent harness](../technical/JEV_AGENT_HARNESS.md).

## What the feature is

- **Input format:** images are ordinary PNG or JPEG files. There is no new image format.
- **Attaching:** a request attaches each image as an *asset*, either a multipart part or `data_base64` plus `format`.
- **Referencing:** a reference string places the image in `state`, `instructions` or `criteria`. The reference is
  plain-text find-and-replace, so references must be unique and unguessable.
- **Answer types:** Choice, Score and Noul all work on images.
- **New `Box` answer:** returns one normalized box with a confidence. A Box answer always returns a box, so pair it
  with a Noul presence question and discard the box below a tuned threshold.
- **Status:** experimental. The report says requests need the opt-in header `TypeSafe-Danger-Zone-Images: true`.

## Verification

| Claim | How it was checked | Result |
|---|---|---|
| Model `jev-1.14.0` is available to this account | Text-only probe through the Jev MCP with `model: jev-1.14.0` | **Verified.** The response reported `jev-1.14.0`. |
| The SDK supports image assets and Box | Read the source of the `typesafe-sdk` 0.7.5 wheel. It was downloaded but not installed or executed. | **Verified.** It has the `Image` asset class, `assets` and `data_base64`, the `Box` answer type and an `extra_headers` hook. |
| Images require the header `TypeSafe-Danger-Zone-Images: true` | SDK source | **Partly.** The header name is not in the SDK. It must be passed through `extra_headers`, as the report shows. |
| Each side 280–1568 px; 16 MiB per file and 32 MiB per request; EXIF stripped and orientation not applied | Report only | **Not verified.** Our crops are already upright (`open_oriented_for_ml`) and at most 768 px. Tiny crops would need padding to 280 px. |
| Price $0.042 per million input tokens; images billed as input tokens | Report only | **Not verified.** At that price a 20-frame pilot costs a fraction of a cent. |

## Current gaps in our tooling

- **The Jev MCP tool cannot send images.** `jev_system_one` and `jev_choice` take `state`, `questions` and `model`,
  but no `assets`.
- **Harness client and installed SDK.** The harness client (`scripts/agent_harness/jev_gate.py`) pins `jev-1.13.0`.
  The installed `typesafe-sdk` is 0.7.1, which predates `Image` and `Box`.
- **Credentials for direct SDK calls.** These need `TYPESAFE_API_KEY` in the calling environment. It is not set in the
  agent shell, and agents must not read it from configuration files.

## Where it would help

1. **Settling split species votes.** On 2026-10-16, species-blind text descriptions with Jev settled only 1 of 7
   split frames at the 0.7 threshold ([list gate](bird-species-list-379-gate-2026-10-16.md)). On 2026-10-12 they
   settled 3 of 31 ([agent-panel gates](localization-agent-panel-gates-2026-10-12.md)). A Choice on the crop itself
   should resolve more frames.
2. **A fifth vision judge or quota fallback.** One panel judge was quota-limited on 2026-10-12. Jev could join the
   blind panel in `scripts/research/judges/species_panel.py`.
3. **Box-quality gates.** A Choice on the crop with the box drawn could grade TIGHT, LOOSE, WRONG or NO_BIRD, as the
   cascade AC-17 panel did (#408).
4. **Not a detector replacement.** Box returns one target per question and never reports "not found". At most it
   can be a research verifier for low-confidence cascade fallbacks, in a hybrid with YOLO and RTMDet.

## Conditions before use

1. **Egress approval.** Private bird-photo crops would go to TypeSafe, a provider the 2026-10-11 crop-egress
   decision did not cover. That decision covered the CLI judges only. It needs the owner's approval and a recorded
   decision. Send crops only, never full frames or file paths. TypeSafe also strips the remaining metadata.
2. **Tooling.**
   - Upgrade to `typesafe-sdk` ≥ 0.7.5 in the judging environment.
   - Make the API key available through the environment.
   - Pin `jev-1.14.0` in every request and record `model`, the question version and `usage.input_tokens`.
3. **Pilot and calibration.**
   - Jev must pass the same pilot as the CLI judges: at least 18 of 20 control frames correct, and parseable answers.
   - The text-mode calibration (92% agreement at confidence ≥ 0.7) does not transfer to images. Image answers need
     their own threshold, set on held-out frames.
4. **No production use** while TypeSafe labels images experimental.

## Next step

After egress approval and key availability, add a `jev` judge to `species_panel.py`. Pin the model, attach the
blind crop as an asset, and ask the same A, B, NEITHER or UNSURE question as the CLI judges. Run it on the 20 pilot
control frames first.
