---
type: Report
title: Keyword, caption and species models — comparison on the #377 cohort
description: Production CLIP B/32 keywords, BLIP captions and BioCLIP 2 species vs a reference design's OpenCLIP B/32 (LAION) scene/species approach and the roadmap candidates (SigLIP2, OpenCLIP L/14, Florence-2), on 339 owner-labelled frames; species disagreements judged by a 4-agent vision panel plus Jev on blind descriptions.
resource: docs/reports/keywords-captions-species-comparison-2026-09-24.md
tags: [research, keywords, captions, species, clip, siglip2, florence2, bioclip, clean-room]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
---

# Keyword, caption and species models (2026-09-24)

> **Status:** research memo, read-only. Models ran in `image-scoring-gpu-shell` on the stored
> thumbnails, orientation baked. No production data changed.
>
> Related:
> - [phase: keywords](../architecture/pipeline/phases/keywords.md)
> - [phase: bird species](../architecture/pipeline/phases/bird-species.md)
> - [model roadmap](../MODEL_RECOMMENDATIONS_PIPELINES.md)
> - [subject detector comparison](subject-detector-comparison-2026-09-24.md), same cohort

## Provenance (clean-room)

One arm reproduces the *approach* of a reference wildlife-culling design, as observed from its
behaviour:
- **Scenes:** a general OpenCLIP ViT-B/32 (LAION-2B) with five photographic scene labels (portrait,
  flight, habitat, action, group). There is no general keyword tagging and no captioning.
- **Species:** zero-shot over an 835-name birds-and-mammals vocabulary on a centre-cropped full
  frame, gated by a confidence threshold. In the product, the user first narrows the candidate list.

We used its published-format text embeddings for that vocabulary as a measurement input only. No code
from the product is involved.

## Setup

- **Frames:** the 339 frames of the [#377 cohort](detector-benchmark-2026-09.md): 238 bird, 99
  no_bird, 2 unsure. Labels are the owner's bird/no_bird presence labels.
- **No human species labels exist.** Species correctness comes from a **blind multi-agent panel**
  on all 193 disagreements (§3b): four CLI vision judges, plus Jev on species-blind text
  descriptions. This is not expert ground truth.
- **Selection bias:** the `miss_birdkw` / `miss_nokw` strata were built from the *production* `birds`
  keyword. Results for the production keyword tower are therefore also reported on the unbiased strata
  (`det_*` + `eagle`: 160 bird, 28 no_bird).
- **Models:**

  | Role | Model | Status |
  |---|---|---|
  | keywords | `openai/clip-vit-base-patch32` | **production** |
  | keywords | OpenCLIP ViT-B/32 `laion2b_s34b_b79k` | reference design's tower |
  | keywords | OpenCLIP ViT-L/14 `laion2b_s32b_b82k` | roadmap unified track |
  | keywords | `google/siglip2-base-patch16-224` | roadmap keyword scorer |
  | species | BioCLIP 2 over `data/bird_species_list.txt` (360 names) | **production** |
  | species | LAION B/32 over the 835-name vocabulary | reference design |
  | captions | `Salesforce/blip-image-captioning-base` | **production** |
  | captions | Florence-2-base (`<CAPTION>`, `<DETAILED_CAPTION>`) | roadmap |

- **Keyword rule:** as in production, `"a photo of {k}"` over the 26 `DEFAULT_KEYWORDS`. For CLIP
  towers, softmax probability ≥ 0.2, top 5. For SigLIP2, sigmoid ≥ 0.5.
- **Caption rule:** a caption counts as "mentions bird" if it contains "bird" or any of ~80 bird-type
  words.

## 1. Is there a bird? (keywords vs captions)

| Arm | Recall, unbiased strata | FP, unbiased | Recall, all strata | FP, all strata |
|---|---|---|---|---|
| stored production keyword `birds` | 98/160 = 61% | 1/28 | 171/238 = 72% | 18/99 = 18% |
| stored `birds \| animals \| wildlife` | 91% | 75% | 92% | 38% |
| OpenAI B/32 re-run, `birds` selected | 68% | 7% | 77% | 11% |
| LAION B/32, `birds` selected | 62% | 4% | 71% | 7% |
| LAION L/14, `birds` selected | 48% | 4% | 54% | 5% |
| SigLIP2, `birds` at sigmoid ≥ 0.5 | 2% | 0% | 1% | 0% |
| BLIP-base caption mentions bird | 97% | 4% | 95% | 10% |
| **Florence-2 caption mentions bird** | **100%** | **4%** | **99%** | **7%** |
| Florence-2 detailed caption | 96% | 4% | 96% | 5% |

**Threshold-free AUC, bird vs no_bird** (`birds` probability):

| Model | Unbiased strata | All strata |
|---|---|---|
| OpenAI B/32 | 0.945 | 0.939 |
| LAION B/32 | 0.968 | 0.950 |
| LAION L/14 | 0.959 | 0.948 |
| SigLIP2 | 0.950 | 0.946 |

At a matched FP ≤ 10% (all strata), recall is:

| Model | Recall |
|---|---|
| OpenAI B/32 | 74% |
| LAION B/32 | 86% |
| LAION L/14 | 94% |
| SigLIP2 | 82% (threshold ~0.013, not 0.5) |

**Reading:**
- **The towers are close; the rule is the problem.** Softmax over 26 competing tags lets `wildlife`,
  `nature` and `forest` absorb the probability mass on bird photos. Production therefore misses about
  a third of labelled birds, and the result depends on the rest of the tag list (the
  `confidence` vs `relevance_weight` caveat in the phase doc).
- **SigLIP2 needs per-tag thresholds** (the roadmap already says so). With the CLIP-style 0.5 rule it
  emits almost nothing.
- **Captions answer "is there a bird" better than any keyword rule.** Florence-2 reaches 99–100%
  recall at 4–7% FP.

## 2. Captions

On the 238 labelled-bird frames:

| Model | Mentions bird | Names a bird type | Mean words | GPU ms / image |
|---|---|---|---|---|
| BLIP-base (production) | 225 | **17 (7%)** | 8.6 | 148 |
| Florence-2-base caption | 236 | 67 (28%) | 9.8 | 136 |
| Florence-2-base detailed | 228 | **171 (72%)** | 29.8 | ~2× caption |

Examples from the same frames:

| BLIP | Florence-2 detailed |
|---|---|
| "a bird perched on a branch in the woods" | "an **osprey** perched atop a tree branch in the woods…" |
| "a bird is standing in the water near a tree" | "a **little blue heron** standing in the water…" |
| "a bird sitting on top of a rock" | "a **bald eagle** perched atop a rocky cliff…" |

**Caveat:** type names in Florence-2 captions were not verified individually, and generative captions
can hallucinate. For species, prefer BioCLIP. Use the caption for description and as a presence and
scene signal.

## 3. Species

**Agreement on the shared 336-name vocabulary** (both models restricted to names in both lists):

| Pair | Top-1 agreement |
|---|---|
| BioCLIP full frame vs BioCLIP YOLO crop | 94/121 = 78% |
| BioCLIP YOLO crop vs BioCLIP open-detector crop | 85/119 = 71% |
| BioCLIP YOLO crop vs LAION B/32 full frame (reference approach) | 47/121 = 39% |
| BioCLIP full vs LAION B/32 full | 65/238 = 27% |
| LAION B/32 full vs LAION B/32 crop | 53/227 = 23% |

The re-run reproduces the stored production species on 134/162 frames (83%). The difference comes
from thumbnails vs source pixels and from the crop path.

**Confidence (median top-1 probability):**

| Model | Median | ≥ 0.5 |
|---|---|---|
| BioCLIP | 0.98 | 83–84% |
| LAION B/32, full frame | 0.34 | 28% |

Applying the reference design's own confidence gate to its full 835 vocabulary without a candidate
list, it **abstains on 228/238** bird frames. Its top-1 is a *non-bird* on 17/238.

### 3b. Multi-agent panel on every disagreement

This replaces an earlier single-assistant check of 30 low-resolution crops. At full resolution, that
check turned out to contain errors: for example, frame 48203 is a Carolina Wren, not the Bewick's Wren
first recorded.

**Panel.** The production design is BioCLIP on the YOLO crop, else the full frame, over the 360-name
list. The reference design is LAION B/32 on the full frame over 835 names. They disagree on
**193 of 238** labelled-bird frames; all 193 went to the panel, plus 20 agreements as a control.

- **Crops:** cut from each RAW's full-size embedded JPEG (35% padding, 768 px).
- **Blinding:** the two candidate names appear as A/B in random order, and the judges' folder
  contains only images, with no manifest.
- **Four vision judges** answered "A / B / NEITHER / UNSURE" plus their own identification:

  | Judge | Coverage |
  |---|---|
  | Claude Code CLI | 213/213 |
  | Codex CLI | 180/213 (usage limit reached) |
  | Antigravity CLI | 213/213 |
  | Cursor agent | 213/213 |

- **One text arm:**
  - A separate agent wrote a species-blind field-mark description of each crop. A leakage check
    found no species or group names.
  - **Jev** (`jev-1.13.0`, via the Jev MCP server) then chose between "A / B / neither / cannot tell"
    from the description text alone.

**Who is right on the 193 disagreements:**

| Judge | BioCLIP | Reference | Neither | Unsure |
|---|---|---|---|---|
| Claude | 131 (68%) | 18 (9%) | 40 | 4 |
| Codex | 121 (67%) | 15 (8%) | 37 | 7 |
| Antigravity | 136 (70%) | 20 (10%) | 34 | 3 |
| Cursor | 144 (75%) | 26 (13%) | 23 | 0 |
| **Vision majority (≥ 3 judges)** | **134 (69%)** | **16 (8%)** | **32 (17%)** | 3 (8 split) |
| Jev on blind descriptions | 109 (56%) | 30 (16%) | 45 (23%) | 9 cannot tell |

**Reliability of the judges:**
- **Controls:** each judge accepts 19/20 agreement cases. Codex did not reach them.
- **Pairwise agreement between vision judges:** 150/180 to 177/193 (83–92%).

**Jev** agrees with the vision majority 138/185 overall. Agreement tracks its confidence:

| Jev confidence | Agreement with vision majority |
|---|---|
| < 0.4 | 25/53 |
| 0.4–0.7 | 42/55 |
| **≥ 0.7** | **71/77 (92%)** |

A confident text-only verdict is a usable cross-check. A low-confidence one is noise, because the
description loses detail that the pixels carry.

**Implied accuracy over all 238 bird frames:** assume agreements are correct at the 19/20 control
rate and take the vision majority as truth on disagreements.

| Design | Accuracy |
|---|---|
| **BioCLIP (production)** | **≈ 74%** |
| general CLIP, reference-style | ≈ 25% |

These are agent-panel judgements, not expert labels.

**Where BioCLIP is wrong** (32 majority-"neither" cases):
- **12 are species absent from `bird_species_list.txt`:**
  - Bewick's Wren ×3
  - Lesser Goldfinch ×2
  - Black-bellied Whistling-Duck
  - Black-crested Titmouse
  - Zone-tailed Hawk
  - Mississippi Kite
  - Great-tailed Grackle
  - Egyptian Goose
  - a domestic goose

  10 of them are in the broader 835-name vocabulary.
- **18 are on the list but misidentified.** 2 have no consensus ID.
- **The crop source doesn't explain the misses.** BioCLIP is right on 60/86 disagreements with the
  YOLO crop and 74/96 on the full frame.

**Reading:**
- **Keep BioCLIP 2 for species.** A general B/32 CLIP is not a species classifier on these photos.
  The reference design only gets away with it because the user supplies a short candidate list first.
- **The idea worth taking is the workflow, not the model:**
  - restrict to a candidate set
  - abstain (open-set veto) instead of forcing a label
  - propagate a confident label across the burst
  - build a folder-level "suggested species" shortlist

  Applied to BioCLIP, these fix exactly the failure seen here.
- **Vocabulary gaps are a real error source.** `threshold=0.1, top_k=1` over 360 names forces a
  wrong-but-confident answer when the true species is missing. Expand the list (for example to a
  regional checklist, ~800 North American birds) and add an abstain path based on a similarity floor
  and top-1/top-2 margin.
- **The crop policy matters** (71–78% agreement between crop variants). This is a Stage 5 question
  for the [localization rollout](../architecture/pipeline/localization-rollout.md). Region-first with
  full-frame fallback remains right, but multi-crop agreement is a useful confidence signal.

## 4. Cost

Median GPU ms per image, RTX 4060 Laptop:

| Model | ms |
|---|---|
| OpenAI B/32 | 8.2 |
| LAION B/32 | 6.0 |
| LAION L/14 | 31.7 |
| SigLIP2-base | 10.9 |
| BioCLIP 2 | 10.6 |
| BLIP-base | 148 |
| Florence-2-base caption | 136 |

## Recommendations

1. **Captions (#421):** trial **Florence-2-base** as the caption model, in shadow. It is the same cost as
   BLIP-base, with better bird presence and far more specific descriptions. Keep BLIP behind config
   until a human spot-check of Florence-2 type names is done.
2. **Keywords (#420):**
   - Before any tower swap, replace the softmax-over-26 selection with **per-tag thresholds on a
     set-independent score**. `relevance_weight` already exists. Calibrate each threshold on labelled
     data; the #377 labels give `birds` for free.
   - Then compare towers at matched FP.
   - LAION L/14 (94% at FP ≤ 10%) is the strongest `birds` tower here, but the sample is small.
   - SigLIP2 only with calibrated per-tag thresholds.
3. **Presence fusion:** "bird present" = caption mentions bird **or** calibrated `birds` tag **or**
   open-detector animal box ([detector report](subject-detector-comparison-2026-09-24.md)). This
   feeds the Stage 5 candidate scope, which is currently the `birds` keyword ∪ regions.
4. **Species (BioCLIP stays; #422, and #413 for other taxa):** the panel gives about 74% vs 25%.
   - **Expand the vocabulary first.** Add the species the panel found missing: Bewick's Wren,
     Lesser Goldfinch, Black-bellied Whistling-Duck, Black-crested Titmouse, Zone-tailed Hawk,
     Mississippi Kite, Great-tailed Grackle, Egyptian Goose, domestic goose. Better still, adopt a
     regional checklist of ~800 names.
   - Add abstention (similarity floor + margin) instead of forcing a top-1 at 0.1.
   - Add burst propagation and a folder shortlist (suggestions only; keep the single-species rule).
   - Evaluate crop variants under Stage 5.
5. **Agent panel as a labelling aid.** The four-judge blind panel was 83–92% self-consistent and
   passed 19/20 controls. Use it to pre-label disagreements, then have the owner review only splits,
   "neither" and low-consensus cases. Jev on blind descriptions is a cheap, auditable text
   cross-check, but only at confidence ≥ 0.7 (92% agreement with the panel). It never overrides
   pixels, as the localization rollout's Stage 6 boundary says.
6. **Labels (#415):** panel verdicts are agent-derived. Owner species labels on about 200 frames, focused on
   the 32 "neither" and 8 split cases, would make the ranking decisive.

## Reproduce

The research instrument lives outside this repo. It built an input bundle (cohort, labels, thumbnail
paths, stored keywords/captions/species, detector boxes), ran all models in `image-scoring-gpu-shell`,
and analysed the results on the host. Adjudication crops and verdicts are kept with the instrument.
