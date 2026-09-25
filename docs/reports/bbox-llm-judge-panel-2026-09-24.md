---
type: Report
title: Bird bounding boxes judged by an LLM-agent panel (#377 cohort)
description: Box-quality grades for bird_detect_v0 at 640 and 1280 and an open COCO detector, from a blind multi-agent vision panel (validated against owner labels) plus Jev on judgement-free box descriptions.
resource: docs/reports/bbox-llm-judge-panel-2026-09-24.md
tags: [research, localization, detector, bird-detection, llm-judge, jev, benchmark]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
---

# Bird bounding boxes judged by an LLM-agent panel (2026-09-24)

> **Status:** research memo, read-only. It extends the [#377 detector benchmark](detector-benchmark-2026-09.md)
> and the [subject detector comparison](subject-detector-comparison-2026-09-24.md). Those measured
> **presence** only. This memo grades **box quality**, which the owner's labels do not cover.
> Relevant to [localization rollout](../architecture/pipeline/localization-rollout.md) Stages 3–4.

## Question

When a detector finds the bird, is the box any good? And can LLM agents grade boxes reliably enough
to stand in for box-level human labels?

## Method

**Boxes.** From the 339 #377 frames, take the **top box per detector**:

| Arm | Detector | Setting |
|---|---|---|
| `yolo640` | `bird_detect_v0`, production | `imgsz=640`, conf 0.25 |
| `yolo1280` | the same model | `imgsz=1280` |
| `rtmdet` | open COCO detector | animal classes, conf ≥ 0.4 else 0.25 |

- YOLO boxes were re-run in `image-scoring-gpu-shell` through `open_rendition_for_ml` +
  `bake_orientation`. The re-run reproduces #377 presence and box counts on **339/339** frames at
  both sizes.
- Boxes with IoU ≥ 0.9 on the same frame are judged once, giving **576 unique boxes**
  (yolo640 150, yolo1280 284, rtmdet 254).
- Pairs of arms whose boxes differ (IoU < 0.7) give **165 pairwise items**.

**Renders.**
- **Single box:** the full frame (1024 px) with one yellow box, beside a zoom of the region, cut from
  the RAW's full-size embedded preview.
- **Pairs:** cyan vs magenta in random order.
- **Blinding:** no detector names appear, and the judges' folders contain images only.

**Vision judges** (CLI agents):

| Judge | Coverage |
|---|---|
| Antigravity | 576/576 |
| Cursor agent | 576/576 |
| Claude Code | 168/576 (monthly spend limit hit) |

Codex was out of quota. Majority rule: ≥ 2 judges agree.

**Grades:**

| Grade | Meaning |
|---|---|
| TIGHT | one whole bird, snug |
| LOOSE | whole bird, box > ~2× the bird |
| PARTIAL | a significant part cut off |
| MULTI | several birds boxed as one |
| WRONG | no bird inside |

Judges also answered whether a bird sits outside the box. For pairs: CYAN / MAGENTA / TIE /
DIFFERENT (each box on a different bird) / NEITHER.

**Text arm.**
- A describer agent wrote a judgement-free description of each box: what is inside, what extends
  past which edge, the fill fraction, and the bird count.
- **Jev** (`jev-1.13.0`, via the Jev MCP server) graded each box from the text alone.

## 1. Are the judges trustworthy?

**Checked against the owner's presence labels:** 112 boxes fall on frames the owner labelled
bird-free, so the only correct grade for them is WRONG.

| Judge | WRONG on bird-free frames |
|---|---|
| Antigravity | 107/112 |
| Cursor | 105/112 |
| Claude (partial run) | 27/32 |
| **Vision majority** | **106/112 (95%)** |
| **Jev (text only)** | **107/112 (96%)** |

**Consistency:**
- Exact grade agreement between judges ranges from 79% to 88%: Antigravity vs Cursor 473/576,
  Claude vs Cursor 148/168, Claude vs Antigravity 132/168.
- 65/576 boxes are majority-split.

## 2. Box quality by detector (vision majority, top box, 238 labelled-bird frames)

| Arm | Boxes | TIGHT | LOOSE | PARTIAL | MULTI | WRONG | Split | No box | **TIGHT / bird frames** | TIGHT when boxed |
|---|---|---|---|---|---|---|---|---|---|---|
| yolo640 | 121 | 88 | 11 | 8 | 9 | 0 | 5 | 117 | **37%** | 73% |
| yolo1280 | 213 | 156 | 6 | 11 | 7 | 7 | 26 | 25 | **66%** | 73% |
| rtmdet | 227 | 150 | 1 | 30 | 3 | 4 | 39 | 11 | **63%** | 66% |

By stratum. Each cell is **TIGHT | TIGHT+LOOSE | bad | no box**, where bad = PARTIAL + MULTI + WRONG.

| Stratum | n | yolo640 | yolo1280 | rtmdet |
|---|---|---|---|---|
| det_small | 48 | **45**\|45\|3\|0 | 38\|38\|3\|0 | 28\|28\|12\|1 |
| det_medium | 36 | 23\|27\|5\|0 | 26\|27\|3\|0 | 23\|23\|4\|0 |
| det_large | 17 | 5\|8\|8\|0 | 5\|5\|9\|0 | **10**\|10\|6\|0 |
| miss_birdkw | 73 | 0\|0\|0\|73 | 37\|41\|9\|17 | **45**\|46\|10\|8 |
| miss_nokw | 5 | 0\|0\|0\|5 | 2\|2\|1\|2 | 3\|3\|2\|0 |
| eagle | 59 | 15\|19\|1\|39 | **48**\|49\|0\|6 | 41\|41\|3\|2 |

**False-positive boxes on bird-free frames:**

| Arm | Boxes | Judged WRONG |
|---|---|---|
| yolo640 | 28 | 26 |
| yolo1280 | 71 | 68 |
| rtmdet | 27 | 26 |

**Pairwise, where boxes differ** (vision majority):

| Pair | Result |
|---|---|
| yolo1280 vs yolo640 | 17–4 (9 neither, 2 different birds, 5 split) |
| rtmdet vs yolo640 | 21–13 (5 neither, 4 different, 9 split) |
| yolo1280 vs rtmdet | **24–24** (12 neither, 9 different, 7 split) |

## 3. Reading

- **On the birds it finds, the production box is good.** 73% of yolo640 boxes are TIGHT. It is best
  on small birds (45/48 TIGHT in `det_small`). Its weakness remains **finding** birds: no box on
  117/238.
- **The open detector's weakness is small subjects**, the mirror image of YOLO's. In `det_small` it
  is TIGHT on only 28/48, with 12 bad boxes, mostly PARTIAL: boxes that clip small birds found on a
  ~800 px rendition. It is best on large birds (10/17 TIGHT vs 5/17 for both YOLO sizes) and on the
  keyword-positive misses (45/73 TIGHT).
- **YOLO at 1280 and the open detector tie on quality** (24–24 head-to-head). But 1280's extra
  presence comes with many more false boxes (71 vs 27, as the #377 and comparison reports showed).
- **Large birds are hard for YOLO at either size.** In `det_large`, 8/17 and 9/17 boxes are bad
  (MULTI or PARTIAL). This is consistent with a training set of CUB-style crops without very large
  or partially framed subjects.
- **The detectors are complementary.** YOLO boxes small birds tightly, and the open detector finds
  and boxes large and missed birds. A **cascade** fits the Stage 3–4 design:
  1. yolo640 box when present
  2. else open-detector box
  3. for small open-detector boxes (< ~2% of the frame), a second YOLO pass on a padded crop to
     tighten them

  This matches the "targeted second pass" already named in Stage 3.

## 4. LLM text judgement (Jev) and the rubric lesson

The first Jev pass agreed with the vision majority on only **338/511** boxes. The confusion was
almost entirely vision-TIGHT → Jev-PARTIAL (146 boxes):
- The descriptions faithfully mention small overhangs (a tail tip past the edge, feet below the box).
- Jev's criteria said "part of it extends beyond", so it called those PARTIAL.
- The vision judges' rubric said "a *significant* part".
- The more literal describer (Antigravity) triggered this twice as often as Claude's descriptions
  (52% vs 29% of TIGHT boxes).

A second pass used the **same descriptions** with the rubric aligned to the vision judges' (tail-tip,
wingtip and feet overhangs don't count; any head or bill cut does). Agreement rose to **421/511
(82%)**, and **384/438 (88%) at Jev confidence ≥ 0.7**. The bird-free check stayed at 107/112.

**Lesson for any LLM-judge pipeline:** the text judge's criteria must be word-for-word consistent with
the vision rubric. Otherwise it measures a different question, and does so confidently.

## Recommendations

1. **Box-level labels can be bootstrapped with the panel.** It is 95% correct on the verifiable
   subset. Route only the 65 split boxes plus a random 10% audit to the owner, instead of hand-drawing
   576 boxes. Add the 2 "different bird" pair categories to the review queue.
2. **For Stage 4 shadow localization, evaluate the cascade:**
   - yolo640, then the open detector as fallback
   - YOLO refine on small fallback boxes
   - measure with this panel (TIGHT rate on bird frames) and the #377 presence labels
3. **Training data for the next `bird_detect_v0`:**
   - large and partially framed birds (MULTI/PARTIAL in `det_large`)
   - the keyword-positive misses, where the open detector's TIGHT boxes (45/73) are ready-made
     pseudo-labels
4. **Jev as a cheap second opinion** on box grades: only with the aligned rubric, and only at
   confidence ≥ 0.7. It stays behind the vision panel, consistent with the Stage 6 boundary that
   text-only models never validate a localization artifact themselves.

## Reproduce

The research instrument lives outside this repo:
- YOLO re-run script for the GPU container
- panel builder, runner, analysis and Jev MCP client

Renders, raw judge outputs and Jev answers are kept with it.
