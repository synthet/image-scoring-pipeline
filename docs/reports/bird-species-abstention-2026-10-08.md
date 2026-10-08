---
type: Report
title: Bird species abstention floor and list gaps (#422)
description: BioCLIP 2 re-run on the 213 judge-panel crops. A 0.5 top-1 floor keeps 92% of frames at 93.5% precision. Adding nine missing species helps in-sample but brings new confident errors. A Jev re-check overturned no panel verdict.
resource: docs/reports/bird-species-abstention-2026-10-08.md
tags: [research, bird-species, bioclip, abstention, llm-judge, jev]
timestamp: 2026-10-08T00:00:00Z
okf_version: 0.2
---

# Bird species abstention floor and list gaps (2026-10-08)

Issue #422 asks two things of `bird_species`: add the species missing from `data/bird_species_list.txt`, and abstain instead of forcing a top-1 label. This report measures both on the frames from the [species judge panel](keywords-captions-species-comparison-2026-09-24.md#3b-multi-agent-panel-on-every-disagreement) and records the shipped thresholds.

## Method

- **Frames:** the 213 panel crops (193 disagreements plus 20 controls), each cut from the RAW's embedded JPEG with 35% padding at 768 px. These are not the production YOLO crops, so the probabilities here are close to production but not identical.
- **Model:** production `BioCLIPClassifier.classify`, run in `image-scoring-gpu-shell` with `use_detector=False`, `threshold=0`, `top_k=5`.
- **Lists:**
  - *base:* the 360 names.
  - *expanded:* the 360 names plus nine more: Bewick's Wren, Lesser Goldfinch, Black-bellied Whistling-Duck, Black-crested Titmouse, Zone-tailed Hawk, Mississippi Kite, Great-tailed Grackle, Egyptian Goose and Domestic Goose.
- **Provisional truth:** the species named by at least 3 of the 4 vision judges in their own identifications. That covers **199 of 213** frames.
  - The labels are LLM judgements, not owner labels.
  - The sample is biased toward hard frames, since it is mostly cases where BioCLIP and a second model disagreed.

## Results

**Top-1 accuracy against the judge consensus**

| List | Accuracy |
|---|---|
| base (360) | 166/199 = 83.4% |
| expanded (369) | 175/199 = 87.9% |

The expanded gain is **in-sample**: the nine species were chosen because they were missing on these frames.

**Floor × margin on the expanded list.** The margin is top-1 minus top-2 probability.

| Floor | Margin | Kept | Precision | Abstained (of which BioCLIP wrong) |
|---|---|---|---|---|
| 0.1 (old default) | 0 | 199 | 0.879 | 0 |
| 0.3 | 0 | 191 | 0.916 | 8 (8) |
| **0.5** | **0** | **184** | **0.935** | **15 (12)** |
| 0.5 | 0.2 | 183 | 0.940 | 16 (13) |
| 0.7 | 0 | 178 | 0.955 | 21 (16) |

On the base list, the same 0.5 floor keeps 174 frames at 0.931.

BioCLIP's temperature-100 softmax is very peaked. Once the floor is applied, a top-1/top-2 margin removes almost nothing more, so **no margin is shipped**.

## Adjudication of confident disagreements

Twelve frames had BioCLIP at p ≥ 0.5 (expanded list) disagreeing with the judge consensus.

- **Excluded (3):**
  - Two had a consensus of "unknown".
  - One is a taxonomy split rather than an error: Woodhouse's Scrub-Jay vs Western Scrub-Jay.
- **Re-checked (9):** Jev (`jev-1.13.0`) chose between the two names, blinded as A/B, from the existing species-blind field-mark descriptions alone.

| Frame | BioCLIP (p) | Panel | Jev |
|---|---|---|---|
| 37282 | Tufted Titmouse (0.78) | Black-crested Titmouse | cannot tell (0.21) |
| 9144 | Great-tailed Grackle (0.99) | Boat-tailed Grackle | panel (0.25) |
| 175445 | Yellow-bellied Sapsucker (0.78) | Ladder-backed Woodpecker | **panel (0.61)** |
| 212363 | American Crow (0.74) | Fish Crow | panel (0.14) |
| 201905 | Mississippi Kite (0.62) | Red-shouldered Hawk | **panel (0.67)** |
| 154357 | Carolina Chickadee (0.90) | Black-capped Chickadee | cannot tell (0.34) |
| 73428 | Forster's Tern (0.68) | Gull-billed Tern | BioCLIP (0.40) |
| 64954 | Great-tailed Grackle (0.91) | Common Grackle | cannot tell (0.60) |
| 9830 | Black-crested Titmouse (0.66) | Carolina Chickadee | cannot tell (0.99): no bird visible |

**What the re-check shows**

- **No panel verdict is overturned.** The precision figures above stand.
- **The expansion adds new confident errors.**
  - Great-tailed Grackle takes two other grackles at p ≥ 0.91.
  - Mississippi Kite takes a Red-shouldered Hawk.
  - Black-crested Titmouse is assigned to a frame with no visible bird.
  - Without a range prior, a longer list trades missing-species errors for look-alike errors.
- **Abstention cannot fix a crop with no bird.** In frame 9830, BioCLIP is confident on an empty crop. That needs a bird-present check upstream; localization provides one.
- **The judges have no range prior either.** Black-capped Chickadee (frame 154357) does not occur in coastal Texas or Florida, where most frames were taken, so BioCLIP's Carolina Chickadee is probably right there. The panel labels are provisional for exactly this reason.

**Codex and Antigravity re-judging was attempted and did not run.** The orchestrator refuses image files, its Codex adapter passes a flag that `codex exec` 0.161 no longer accepts, and Antigravity's headless mode denied the tool it needed to open an image.

## Production impact

Read-only, live database, 2026-10-08:

| Measure | Count |
|---|---|
| Bird-tagged images with a stored `bioclip` species | 16,301 |
| Of those, top-1 confidence < 0.5 | **3,614 (22%)** |

So with the floor, about one in five future species runs on bird-tagged images will abstain.

- Existing keywords are not changed.
- `BIRD_SPECIES_RUNNER_VERSION` is not bumped, so earlier `no_species_match` skips are not re-run against the new list.
- On this biased sample, BioCLIP was right on only 3 of the 15 frames below 0.5. Accuracy below 0.5 on the full library has not been measured.

## Shipped

- **`data/bird_species_list.txt`:** the nine species, in their own commented section.
- **`bird_species.min_confidence`** (default `0.5`): the threshold for jobs that do not pass one.
  - Below it, no `species:*` keyword is written, and the image is recorded as `skipped` / `no_species_match`, the existing exhausted path.
  - A separate "uncertain" status was not added. A new skip reason would make abstained images eligible again on every run.
- **Callers:** `threshold` is now optional in the REST request, the job dispatcher and the MCP tool. An explicit threshold still wins.

## Not done

- **A range-aware regional checklist** (~800 names, with source and licence). That is the real fix for list gaps and would replace the ad-hoc additions above.
- **Burst propagation and the folder shortlist** (#422 items 3–4).
- **Owner labels** for any of these frames.
- **Codex and Antigravity re-judging** through the orchestrator, until its image handling and Codex flags are fixed.
