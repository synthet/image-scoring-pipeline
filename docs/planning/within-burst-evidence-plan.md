---
type: Plan
title: Within-burst evidence — no-LLM arm and DepictQA-Wild arm
description: Two-arm plan to test whether crop-conditioned or paired-comparison quality evidence separates frames within a burst; Arm A (no new model) is the control, Arm B (DepictQA-Wild) is gated behind it.
resource: docs/planning/within-burst-evidence-plan.md
tags: [docs, planning, culling, evidence, iqa, depictqa, typesafe, bird_bbox]
timestamp: 2026-09-21T00:00:00Z
okf_version: 0.1
---

# Within-burst evidence: no-LLM arm + DepictQA-Wild arm

> **Status:** proposal, not approved. No code written, no issue filed. Read-only research plan.

## Context

Three research notes converge on one finding: the culling pipeline's decision layer has never
been given evidence that distinguishes frames *within* a burst.

- Captions collapse within stacks — 46.4% of stacks share one identical caption across every
  frame, 37.5% are missing, 29.7% of picks share a caption with a reject in the same stack.
  Adding captions to scores moved folder-grouped ROC-AUC from 0.627 to 0.627.
- The Phase-0 Jev arm (5,893 calls, `jev-1.13.0`) scored 0.256 label agreement, **0.017 pick
  recall**, log loss 5.206, Brier 0.997 — near chance — while returning 5,893/5,893 structurally
  valid responses with zero invalid probability sums. Typed output guaranteed the interface, not
  the truth.
- `reports/typesafe-culling-real-data/summary.md` names the cause: *"pairwise visual differences
  were not supplied."*

Every rubric in `modules/typesafe/rubrics.py` is a *non-quality* axis, and two explicitly forbid
the quality axis — `culling.distinctiveness` says *"do not infer focus, sharpness, noise, or
exposure"*, `culling.action` says *"Do not infer visual properties that the evidence does not
report."* Those prohibitions were right, because nothing in the state reported quality. The
decision layer was barred from the one dimension that separates frames of a burst.

Two candidate fixes exist, and they cost wildly different amounts:

- **Arm A (no-LLM):** the whole-frame scores are flat within a burst (SPAQ 72–77, LIQE 74–95
  across 60 frames, no correspondence to eye sharpness) because they describe the *scene*, and
  every frame in a burst is the same scene. Re-scoring the **subject crop** and relativizing
  **within stack** attacks that directly with models already in the stack. The crop study
  measured 2.42×–17.51× more sensitivity to subject-only degradation, with **21.2% of
  within-burst labels flipping**.
- **Arm B (DepictQA-Wild):** a 7B generative VLM giving natively *paired* non-reference quality
  comparison (`quality_compare_noref`) plus a pixel-conditioned confidence.

**Intended outcome:** run both on the same crops and the same splits, with Arm A as the cheap
control, and find out whether a 7B VLM is actually needed. Arm A is a prerequisite for Arm B
anyway — both consume the same crops — so building it first costs almost nothing extra.

## Decisions taken

- **Both arms, Arm A first as control.**
- **Stack cap raised** to cover real bursts (the 60-frame burst is currently excluded entirely by
  `COUNT(*) BETWEEN 2 AND 10`). Consequence: **the 0.658 `all_evidence` number does not transfer**
  and must be re-measured on the new cohort before it can gate anything.
- **GPU strategy for Arm B is open** (see [Open decision](#open-decision)). It blocks only B1;
  every shared stage and all of Arm A proceed without it.

## Shape

```
S0 board ─ S1 crops ─ S2 re-baseline at new cap   ← shared, no GPU decision needed
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        ARM A (no-LLM)          ARM B (DepictQA)
     crop re-score +            B1 spike ─ B2 pairs
     within-stack z            (needs GPU decision)
              │                       │
              └───────────┬───────────┘
                          ▼
                 S3 joint evaluation
              all arms, same splits, bootstrap CIs
```

**Out of scope, needs a fresh plan afterwards:** the Jev arm (Arm C), any
`modules/typesafe/rubrics.py` version bump, any production integration, any `config.json` key.
Read-only throughout: no DB write, no image mutation, no `modules/` runtime change, no migration.

## S0 — Board (no code)

[`CLAUDE.md`](../../CLAUDE.md) forbids work without an issue. File four in
`synthet/image-scoring-backend`, `area:python` + `priority:p1`, added to Project #1 at
`Stage = Ready`:

1. `research(culling): subject-crop pixel source + provenance` — S1
2. `research(culling): re-baseline culling evidence at raised stack cap` — S2
3. `research(culling): Arm A — crop-conditioned, within-stack-relative scores` — Arm A
4. `research(culling): Arm B — DepictQA-Wild paired quality evidence` — Arm B

Reference IDs ([`docs/project/00-backlog-workflow.md`](../project/00-backlog-workflow.md) §5):
project node `PVT_kwHOAFXgIs4BWC3c`, Stage field `PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0`, options
`Ready=ddaf7773`, `Claimed=1cc70f0b`, `In Progress=8b22e18e`, `Blocked=4bbe5dd0`,
`Review=cb723acb`. Claim via `/task-claim <N>`; flip to `In Progress` on first commit; PR body
carries `Closes #<N>`.

## S1 — Crops and provenance (shared by both arms)

### Almost all of this already exists — reuse it

`scripts/research/bird_crop/` already implements the full crop stack. Do **not** write a new
pixel-extraction module; wire these together instead:

| Existing helper | What it already does |
|---|---|
| `bbox.py: parse_bbox()`, `is_not_detected()`, `is_scan_failed()` | distinguishes the three `bird_bbox` states properly |
| `bbox.py: BirdBox.area_frac`, `subject_px_at_long_edge()`, `count_edges_touched()` | the sanity signals a filter needs |
| `bbox.py: padded_box()` | padding **and** a documented whole-frame fallback on a degenerate result |
| `crops.py: load_oriented()`, `rescale_box()`, `crop_for_variant()`, `load_variant()` | EXIF-oriented decode → crop → resize, matching what `bird_species` does |
| `crops.py: parse_variant()` | variants `full`, `crop` (pad 0.10), `croppad<pct>`, `cropctx<k*10>`; raises on a typo so a mislabelled full-frame run cannot happen silently |
| `crops.py: CropResult` | already carries the provenance the analysis must control for — `crop_scale_factor` (<1 means the crop was upscaled to reach model input, "a known IQA confound, so it is recorded rather than hidden") and `aspect` |
| `af_metadata.py: read_af_batch()`, `af_box_in_display_space()`, `af_bird_agreement()`, `availability()` | batched exiftool AF read, EXIF-orientation-corrected, reusing `modules.exif_extractor._get_exiftool_path()` |

The RAW path is handled too: `crops.py` documents the decode chain as embedded JPEG ≥1000 px →
rawpy, so no separate `exiftool -b -JpgFromRaw` step is needed.

**Correction to an earlier note:** `modules/bird_detection.py:224` *does* write `area_frac` into
`bird_bbox`. Older rows predate it. Read it when present, fall back to computing
`((x2-x1)*(y2-y1)) / (img_w*img_h)` — `BirdBox.area_frac` already does exactly this.

### Does the detector work? Partly — and the failure is not random

This is the load-bearing risk for both arms, and it is already measured.

**Library-wide** ([`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md),
post-backfill settled figures): **37,417** images with a real box, **29,068** carrying the
not-detected sentinel, **0 NULL** — a **56.3%** detection rate.

**On hard material**
([`bird-detection-recall-2026-09-07.md`](../reports/bird-detection-recall-2026-09-07.md), A41
bald-eagle shoot): the detector **missed 39 of 59 frames**, every one visibly containing a large
unobscured eagle. Not errors — `{"detected": false}`, meaning YOLO ran and returned nothing.

| Group | n | median `area_frac` | approx. subject long side at `imgsz=640` |
|---|---|---|---|
| Detected | 20 | 0.0590 | ~155 px |
| Missed (hand-measured) | 39 | 0.0140 | ~76 px |

The populations separate almost cleanly at **`area_frac` ≈ 0.04**. Mechanism: `imgsz=640`
(`_DEFAULT_IMGSZ`, `modules/bird_detection.py:44`) against a 5392 px decode is an **8.4×
downscale**, putting a typical long-lens subject at the small-object limit.

**Three consequences that bear directly on this plan:**

1. **Misses correlate with content, not chance.** Flight-against-sky detected;
   perched-on-sandstone missed. In a mixed burst, crop availability then varies *within* the stack
   by behaviour — which is exactly the coverage-correlates-with-label confound the evaluation must
   already guard against.
2. **The 2.42×–17.51× crop-sensitivity premise was measured on a box-having population**, which
   the recall report itself flags as biased toward larger subjects with conclusions that "may not
   transfer to typical long-lens frames." Treat it as a hypothesis to re-test on the culling
   cohort, not as an established number.
3. **Degenerate boxes exist.** `DSC_2169` has `area_frac` 0.9314 at `conf` 0.66 — 93% of the
   frame. An `area_frac` ceiling ≈ 0.9 catches it.

### Therefore: a crop-source cascade, not bbox-or-nothing

Never exclude a frame for lacking a box — that would bias which frames get evidence at all.
Resolve each frame through an ordered cascade and record which rung fired as `crop_source`:

1. **`bbox`** — real box passing an `area_frac` floor/ceiling and an edges-touched check.
2. **`af`** — AF area from EXIF via the existing `af_metadata.read_af_batch()` /
   `af_box_in_display_space()`, converted to a fixed-size box around the AF centre. This rung
   matters: AF geometry was available on **216/236 (91.5%)** of pinned images and its centre fell
   inside the detected bird box **158/216 (73.1%)** of the time, so it is a detector-independent
   locator with far better coverage than the detector on hard material. It was independently
   judged *"add complementary"* at delta AUC 0.2175.
3. **`centre`** — fixed central crop, for frames with neither box nor AF.
4. **`full`** — whole frame.

Then **stratify every downstream result by `crop_source`**, and report the cascade histogram
before any arm is believed.

### Cheap detector fix worth testing first

`imgsz` is a **config key**, not code — `self.imgsz = int(config.get("imgsz", _DEFAULT_IMGSZ))`
(`modules/bird_detection.py:144`). Re-running detection at `imgsz=1280` over a sample of
`{"detected": false}` rows is the cheapest test of the whole mechanism, costs no code change, and
if recall jumps it materially improves rung 1 coverage for both arms. Recommended as the first
task in S1. Note this would be a **write** to `bird_bbox` if persisted — so run it to a research
sidecar first, read-only against production, and treat any backfill as a separate decision.

### Rendering caveat, still open

The embedded JPEG reflects in-camera picture style and white balance, not what the culler saw in
their RAW processor when they set `pick_status`. Both arms would judge a different rendering than
the label was based on. Sample ~20 frames across picks and rejects before committing to a full run.

Crops land under gitignored `.agent/scratch/` (`.gitignore:282`).

## S2 — Re-baseline at the raised cap

Because the cap moves, **the standing numbers are void** and must be regenerated. Run
`scripts/research/typesafe_culling/real_data_baseline.py` at the new cap.

Recommended: **`--max-stack-size 60`**, and report **two cohorts** in the same run —
`cap10` (the comparability anchor, must reproduce `scores` ≈ 0.627 and `all_evidence` ≈ 0.658) and
`cap60` (the new primary). If `cap10` fails to reproduce, everything downstream is void and the
drift must be found first.

`_selected_stacks_sql` (`real_data_baseline.py:63`) needs no change beyond the existing
`--max-stack-size` flag; it already requires at least one `pick_status = 1` **and** one
`pick_status = -1` per stack.

**Pre-flight, one query:** stack-size histogram plus `SUM(n*(n-1)/2)` over selected stacks, so the
Arm B comparison budget is known before any GPU time is spent.

## Arm A — no-LLM crop-conditioned, within-stack-relative (the control)

No new model, no new dependency, no quantization, no network. This is the cheap hypothesis test
and it might be sufficient on its own.

**A1 — re-score the crops** with the IQA heads already in the stack (`liqe`, `topiq`, `arniqa`,
`spaq`, `koniq`, `paq2piq` per the map at `export_phase0_evidence.py:33-39`), writing to a
research JSONL — **not** to `image_model_scores`, which stays untouched.

**A2 — relativize within stack.** For every score column, emit the within-stack z-score and the
within-stack rank alongside the absolute value. This is the transformation that attacks the actual
failure: absolute values are flat across a burst, relative ones need not be.

**A3 — variants.** `crop_scores` (absolute, crop-conditioned), `crop_scores_relative` (z-scores
and ranks), and `all_evidence_plus_crop_relative`.

Recommendation: run A2's relativization over the *existing* whole-frame scores too, as a free
ablation. It separates "crop conditioning helped" from "relativization helped", which are
different claims and would otherwise be confounded.

## Arm B — DepictQA-Wild paired evidence

### B1 — feasibility spike (blocked on the open GPU decision)

`src/infer.py` hardcodes `model = model.eval().half().cuda()`. Vicuna-v1.5-7B fp16 is ~13.5 GB
before CLIP ViT-L-14, KV cache or vision tokens; the local card is an 8 GB RTX 4060
(`docs/architecture/pipeline/phases/scoring.md:91` already warns against concurrent heavy
inference in `webui` and `gpu-shell`). **fp16 does not fit locally — this is a patch, not a flag.**

Weights: HF publishes **delta weights only** — `zhiyuanyou/DepictQA2-Abstractor-DQ495K` `ckpt.pt`
is 0.14 GB. Base `lmsys/vicuna-7b-v1.5` (~13.5 GB) and CLIP `ViT-L-14.pt` download separately into
the `hf_cache` / `torch_cache` volumes. Use the **Abstractor** variant: `num_query: 64` tokens per
image regardless of resolution, so a pair costs 128 vision tokens.

Minimal-diff quantization: quantize **only the Vicuna backbone** via
`AutoModelForCausalLM.from_pretrained(..., quantization_config=BitsAndBytesConfig(
load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16,
bnb_4bit_use_double_quant=True))`, leave CLIP and the abstractor/projection layers in fp16, and
branch around the two offending lines so bitsandbytes layers are not re-cast.

**The spike's real purpose is the confidence, not the answer.** The design depends on
`prob[idx+1]` — the probability of a single A/B token. A quantization regression here is dangerous
because it is *invisible*: argmax can stay correct while the magnitude collapses toward 0.5 or
saturates, silently corrupting the feature without ever producing a wrong text answer.

Validation experiment, thresholds fixed **before** running:

1. Hold out 100–200 comparisons **outside** the CV cohort, so validation neither burns eval budget
   nor contaminates the result.
2. Run each condition **twice** first, to separate bitsandbytes kernel non-determinism from
   quantization error.
3. Compare fp16 vs 4-bit on identical prompts/images at `temperature: 0.0`.
4. Pass: (a) discrete-answer agreement ≥ **90%**; (b) on agreeing cases, Spearman(confidence)
   ≥ **0.8** and median |Δconfidence| ≤ **0.05**; (c) the `None`-confidence rate rises by no more
   than a few points.
5. On failure, in order of preference: 8-bit instead of NF4 (materially better calibration
   preservation), rent fp16 time for this arm only, or **degrade the feature to the discrete
   win/loss decision** — a binary outcome is far more robust to a small logit shift than a
   probability is. Do not ship the magnitude if it did not survive.

### B2 — comparison export

**Schedule: randomized near-regular, not a seeded tournament.** A bracket seeded by
`score_general` gives ~half the frames exactly one comparison (a single maximally-noisy Bernoulli
draw) while finalists get `log2(n)` against progressively tougher opponents, so win-rate is not
comparable across frames. Worse, the comparison graph of a single-elimination bracket is a *tree* —
the sparsest connected graph — and because seeding follows `score_general`, the resulting estimate
error is itself score-rank-correlated, laundering the very signal the arm is supposed to test
independently.

Instead: full round-robin where affordable (mean stack is 5.03 frames → ≤10 comparisons), and for
larger stacks compare each frame against `min(n-1, B)` others chosen **uniformly at random** with
a fixed seed, `B ≈ 6–8`. Cost is O(n·B) rather than O(n²) — the 60-frame burst becomes ~240
comparisons instead of 1,770 — degree is even across frames, and the schedule is decoupled from
`score_general`.

**Control position bias:** run each pair in both orders, or randomise assignment with a fixed
seed, and record `order` per row.

**Query must be in-distribution.** `build_datasets/scripts/gen_json_refAB_brief.py` defines the
training template pool and the constant
`single_q_tail = " Answer the question using a single word or phrase."`. Pin one template verbatim:

> `Which image do you believe has better overall quality: Image A or Image B? Answer the question using a single word or phrase.`

This also avoids a **2× cost trap**: `cal_confidence_compare_brief` checks the query for one of
`["single word","one word","a word","single phrase","one phrase","a phrase"]` and, if absent,
appends the tail and calls `model.generate` a **second time**. Set `max_new_tokens ≈ 16` rather
than the config default of 400. Record the template as `query_version`.

**Invocation.** Write meta JSON records `{id, image_ref: null, image_A, image_B, query}` with paths
**relative to `cfg.data.root_dir`**, then shell out per batch to `python src/infer.py --cfg <cfg>
--meta_path <meta> --dataset_name <name> --task_name quality_compare_noref --batch_size <n>` and
read the answers JSONL from `cfg.infer.answer_dir`. Batch large — model load dominates and
`infer.py` loads once per invocation. The FastAPI worker in `src/serve/` is for the Gradio demo
and does **not** emit confidence; the batch path is the only one that does.

**Resumability is mandatory**, not optional: a mid-run OOM on a large burst must not redo expensive
work. Mirror `_read_completed()` at `scripts/research/typesafe_culling/run_jev_phase0.py:46-58` —
read back the `set` of hashes with `status == "success"`, append mode, `flush()` per line, and
record per-row failures as `status: "failed"` rather than raising.

**Row schema** (`depictqa-pairwise/1`): `comparison_hash`, `stack_id`, `image_a_id`, `image_b_id`,
`order`, `winner`, `confidence` (nullable), `crop_source` for both sides, `model_id`,
`quantization`, `query_version`, `status`.

**Never send labels.** `pick_status` must not appear in any meta JSON or query, mirroring
`_model_state`'s stripping of `historical_label` in the Jev runner.

### B3 — aggregation

**Decide `confidence is None` before writing the code.** It is a normal outcome — the computation
sits inside a bare `except:` and the token scan (`[7084, 319]` = "Image A", `[7084, 350]` =
"Image B") raises `IndexError` on an unexpected answer form. Recommendation: the comparison still
counts as a win/loss at weight 1 for the unweighted feature, and is **excluded** from the
confidence-weighted feature. Never impute it as 0.5.

**Use regularized Bradley-Terry or Rank Centrality, not raw win-rate.** Unregularized BT-MLE
diverges to ±∞ for undefeated and winless frames, which will happen often at low `B`. Rank
Centrality is the more robust choice on sparse irregular graphs.

**Emit two columns, not one:** the strength estimate and `games_played`, so
`SimpleImputer(..., add_indicator=True)` at `real_data_baseline.py:199-205` can down-weight
low-evidence frames instead of treating a 1-game and an 8-game estimate as equally trustworthy.

## S3 — Joint evaluation and the gate

**Keep orchestration out of the baseline module.** Each arm writes a small JSONL of
`{image_id, <features…>}` — same convention as the existing `export_phase0_evidence.py` →
`run_jev_phase0.py` → `analyze_jev_phase0.py` chain. Then make **one additive change** to
`scripts/research/typesafe_culling/real_data_baseline.py`: optional `--arm-evidence PATH`
(repeatable) that left-joins those JSONLs onto `records` by `image_id` before the matrix is built,
plus new `variants` entries.

This is the load-bearing decision. `_evaluate_variant(matrix, y, groups, columns)`
(`real_data_baseline.py:193`) takes a plain numpy matrix and `variants` (`:404`) is a plain dict,
so reuse is cheap — and it guarantees every arm is measured on **exactly** the same
`StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` folds, the same
imputer/scaler/LogisticRegression pipeline and the same `_safe_metric` wrapper as the number it
must beat. A hand-rolled second CV loop with a different `random_state` or imputation would make
"beats baseline X" meaningless without anyone noticing. Heavy IO (exiftool subprocess, GPU venv
shell-out) stays in the new package, so the small pure-sklearn baseline module keeps its blast
radius.

**Variants to report** (all on both `cap10` and `cap60`):

| Variant | Question it answers |
|---|---|
| `scores` | sanity reproduction |
| `all_evidence` | the number to beat at this cap |
| `crop_scores` | did crop conditioning alone help? |
| `crop_scores_relative` | did relativization alone help? |
| `all_evidence_plus_crop_relative` | **Arm A** |
| `depictqa_only` | is the paired channel informative standalone? |
| `all_evidence_plus_depictqa` | **Arm B** |
| `all_evidence_plus_both` | do they add, or is one redundant? |

**Measure each new feature against `scores` (0.627) as well as `all_evidence` (0.658).**
`all_evidence` already contains within-stack-relative features (`novelty:*` is nearest-neighbour
distance to stack siblings; `caption_uniqueness` is `1/caption_count` within stack), so
collinearity can make a real contribution look smaller than it is.

**The gate needs confidence intervals, not point estimates.** 0.627 → 0.658 is a 0.031 AUC gap on
328 folder groups; a single 5-fold run at `random_state=42` cannot establish a further delta over
it. Compare **bootstrapped or multi-seed AUC distributions** (recommend ≥20 seeds), and report the
delta with an interval. A point estimate that happens to exceed 0.658 is not a pass.

**Stratify** by `crop_source` and confidence band, and report coverage — what fraction of frames
got each feature at all.

**Missingness caution.** `add_indicator=True` adds a missingness column. If coverage correlates
with anything label-related, that indicator carries signal unrelated to quality. Report every arm
**with and without** the indicator, and report coverage stratified by label.

**Known limitation to record in the existing `limitations` list (`real_data_baseline.py:474-479`),
not to "fix":** `pick_status` is a within-stack relative judgment and so is any win-rate or
z-score feature. Two independent relative rankings over a small group (mean n≈5) agree somewhat by
combinatorics alone, which inflates absolute AUC for *any* rank-derived feature. This is
pre-existing in the harness — it applies equally to `novelty:*` and `caption_uniqueness` — and it
is not label leakage: DepictQA and the IQA heads never see `pick_status`, and folder-grouped CV
keeps whole stacks inside one fold, so a test frame's comparison partners are always in the test
fold too.

**Verdict vocabulary** — reuse `scripts/research/bird_crop/report.py:41-44` exactly:
`REPLACE = "replace full-frame"`, `COMPLEMENT = "add as complementary signal"`,
`NO_BENEFIT = "no benefit"`, `UNMEASURED = "not yet measured"`, with ground-truth standing tagged
`human` | `agent-derived` | `constructed` | `derived`.

**Pre-registered falsifiers**, written down before running:

- Arm A ≤ `all_evidence` at the same cap → crop conditioning and relativization do not carry
  within-burst signal; the cheap hypothesis is dead.
- DepictQA within-stack pairwise agreement with `pick_status` ≈ 0.5 → stop at B2, do not evaluate.
- Arm B ≤ Arm A → the 7B VLM is not earning its cost; ship Arm A and close Arm B.
- Any arm that passes only with the missingness indicator included → coverage artefact, not signal.

## Open decision

**GPU strategy for Arm B** (deferred; blocks only B1):

| Option | Trade |
|---|---|
| **4-bit NF4 locally (recommended)** | Everything stays on your machine, minimal patch. Risk is exactly what B1 measures. |
| fp16 on CPU | Exact, no quantization question, ~100× slower — viable for the 100–200 pair validation set, not for bulk. |
| Rent a 24 GB GPU | fp16 throughout, question disappears; crops leave the machine, costs money per run. |

Note the third option is also the natural source of the **fp16 reference arm** that B1's validation
needs, since fp16 Vicuna-7B cannot run on the 4060 at all. A hybrid — rent briefly for the fp16
reference, run bulk locally in 4-bit — may be the cheapest path to a trustworthy answer.

## Files

New package `scripts/research/depictqa/` (needs `__init__.py`; `scripts/` and `scripts/research/`
are implicit namespace packages, leaf packages are real):

| Path | Role |
|---|---|
| `__init__.py` | package marker + layout docstring, mirroring `bird_crop/__init__.py` |
| `prod.py` | read-only DB: `connection()` / `select()` / `assert_prod()` copied from `scripts/research/bird_crop/prod.py`, keeping `conn.set_session(readonly=True, autocommit=True)` and the `RuntimeError("SAFETY: ...")` guard |
| `crop_source.py` | **thin** — the 4-rung cascade only. Delegates to `bird_crop.bbox` (`parse_bbox`, `padded_box`, `area_frac`), `bird_crop.crops` (`load_variant`, `CropResult`) and `bird_crop.af_metadata` (`read_af_batch`, `af_box_in_display_space`). Emits `crop_source` provenance. No new decode, padding or exiftool code. |
| `schedule_pairs.py` | round-robin + budget-capped random scheduling (pure, no IO) |
| `run_depictqa.py` | meta-JSON writer, subprocess invocation, answers ingestion, resumable JSONL |
| `aggregate_pairs.py` | comparisons → strength + `games_played` (pure, no IO) |

New package `scripts/research/crop_rescore/` for Arm A: `rescore_crops.py` (IQA heads over crops),
`relativize.py` (within-stack z-score/rank, pure, no IO).

Modified:

| Path | Change |
|---|---|
| `scripts/research/typesafe_culling/real_data_baseline.py` | `--arm-evidence PATH` (repeatable) left-join by `image_id`; new `variants`; bootstrap/multi-seed CI reporting; one new `limitations` entry |
| `requirements/requirements_depictqa.txt` | **new**, isolated deps, header convention copied from `requirements/requirements_student_scorer.txt` |
| `scripts/docker_gpu_shell_bootstrap.sh` | `INSTALL_DEPICTQA=1` branch alongside the existing `INSTALL_STUDENT_SCORER=1` at line 25 |

**Not touched:** any file under `modules/`, `migrations/`, `config.json`, `requirements.txt`,
`modules/typesafe/rubrics.py`, `image_model_scores`.

**Dependency isolation.** `requirements.txt` has no `transformers`, `peft`, `accelerate`,
`bitsandbytes`, `easydict`, `bigmodelvis` or `sentence-transformers`. Do not add them. Repo code
never imports DepictQA; it runs out-of-process in the persistent venv at `/root/.venvs/research`
on the `gpu_shell_home` volume. Keep Vicuna weights out of the repo and out of any redistributed
artifact — DepictQA code and deltas are Apache-2.0, but the base weights carry LLaMA-2 terms.

## Tests

Flat in `tests/` (repo convention — there is no `tests/research/`), collected by the fast subset,
needing no GPU, DB, network or model weights. Follow the stubbing pattern in
`tests/test_typesafe_client.py`: fake the external surface rather than calling it — here, fake the
answers JSONL on disk under `tmp_path`; the subprocess is never spawned.

| File | Assertions |
|---|---|
| `tests/test_depictqa_schedule_pairs.py` | `test_round_robin_emits_n_choose_2`; `test_budget_cap_gives_even_degree`; `test_schedule_is_seed_stable`; `test_schedule_independent_of_score_order` (guards the seeding bias); `test_singleton_stack_emits_nothing` |
| `tests/test_crop_source_cascade.py` | `test_rejects_degenerate_box_area_frac_0_93` (the documented `DSC_2169` case); `test_area_frac_read_when_present_computed_when_absent`; `test_detected_false_distinct_from_null_and_from_error`; `test_cascade_falls_through_bbox_af_centre_full`; `test_never_excludes_a_frame`; `test_crop_source_recorded_for_every_rung` |
| `tests/test_depictqa_aggregate.py` | `test_strength_finite_for_undefeated_frame` (regularization guard); `test_games_played_emitted_alongside_strength`; `test_confidence_none_counts_unweighted_excluded_weighted`; `test_both_orders_cancel_position_bias` |
| `tests/test_depictqa_meta_format.py` | `test_meta_paths_relative_to_root_dir`; `test_query_contains_single_phrase_tail` (guards the 2× cost trap); `test_meta_never_contains_pick_status` |
| `tests/test_crop_rescore_relativize.py` | `test_zscore_constant_stack_is_zero_not_nan`; `test_rank_is_dense_and_stable`; `test_singleton_stack_handled` |

## Verification

1. **Unit** — `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`
   (add `--ignore=tests/test_exifread.py` if collection fails on optional deps).
2. **Lint** — `ruff check scripts/research/depictqa scripts/research/crop_rescore tests/test_depictqa_*.py tests/test_crop_rescore_*.py`.
   No repo ruff config; defaults apply, lint only touched paths.
3. **Safety** — confirm `assert_prod()` raises against the E2E DB on port 5433, and that a full run
   leaves `git status` clean apart from `reports/` (`.agent/scratch/` is ignored).
4. **Anchor** — S2 must reproduce `scores` ≈ 0.627 and `all_evidence` ≈ 0.658 on the `cap10`
   slice. If it does not, stop and find the drift; every later comparison is void without it.
5. **Pre-flight** — stack-size histogram and exact comparison count recorded before any GPU time.
6. **Cascade coverage** — `crop_source` histogram over the culling cohort, and the same histogram
   split by `pick_status`. If `bbox` coverage differs materially between picks and rejects, the
   confound is real and must be reported alongside every arm, not discovered afterwards.
7. **`imgsz` sweep** — re-run detection at 1280 on a sample of `{"detected": false}` rows to a
   research sidecar (never writing `bird_bbox`) and report the recall delta.
8. **Rendering spot-check** — ~20 NEF previews across picks and rejects, eyeballed against the RAW
   rendering, before committing to a full run.
9. **B1 spike** — the 100–200 pair fp16-vs-4-bit comparison with the thresholds above, run twice
   per condition.
10. **End-to-end** — `docker compose --profile gpu-shell up -d db gpu-shell`, then
    `scripts\batch\docker_gpu_run.bat` per stage, `GPU_SHELL_DETACH=1` for long runs. Never run B2
    concurrently with `webui` on the 8 GB card.
11. **Gate** — bootstrapped/multi-seed AUC distributions for every arm in one run, with intervals,
    not point estimates.

## Risks

| Risk | Mitigation |
|---|---|
| Raised cap changes the cohort and voids 0.658 | S2 re-baselines and keeps `cap10` as an anchor |
| **Detector recall is 56.3% library-wide and content-correlated** (perched missed, flight detected) — crop availability varies *within* a stack by behaviour | 4-rung cascade so no frame is excluded; `crop_source` stratification mandatory; `imgsz=1280` sample test first |
| The 2.42×–17.51× crop premise was measured on a box-having (large-subject) population | re-test it on the culling cohort; treat as hypothesis, not established |
| Degenerate near-full-frame boxes (`area_frac` 0.93) | `area_frac` ceiling ≈ 0.9 + edges-touched check |
| 4-bit silently flattens the A/B probability | B1 measures it explicitly; fallback to 8-bit, rented fp16, or discrete win/loss |
| Seeded schedule launders `score_general` into the feature | randomized near-regular design; `test_schedule_independent_of_score_order` |
| BT diverges on undefeated/winless frames | regularized BT / Rank Centrality; `test_strength_finite_for_undefeated_frame` |
| Embedded JPEG ≠ what the culler saw | spot-check before the full run |
| Coverage correlates with label → fake gain | every arm reported with and without the missingness indicator |
| Declaring a win on a point estimate | CIs mandatory at the gate |
| Silent 2× inference cost | `test_query_contains_single_phrase_tail` |
| Scope creep into the Jev arm | Arm C explicitly excluded |

## Rollback

Nothing to roll back by construction. Two new directories under `scripts/research/`, new test
files, one additive change to one research script, one new requirements file, one bootstrap
branch. Artifacts go to gitignored `.agent/scratch/`; markdown summaries to tracked `reports/`.
Reverting is deleting the directories and one diff. `typesafe.enabled` stays `false`; no DB
session is ever opened writable.

## Carried caveats

The 236-image bird-crop verdict set (60 best / 105 good / 71 reject) is **agent-derived, not
human**. Historical `pick_status` values are behaviour targets, not proof that deletion was safe.
Every AUC this plan produces inherits both.

## Related

- [`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md) — crop premise and pinned population
- [`bird-detection-recall-2026-09-07.md`](../reports/bird-detection-recall-2026-09-07.md) — detector recall floor
- [`BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](../reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) — classical focus measures at chance; AF geometry
- `reports/typesafe-culling-real-data/` — the 0.627 / 0.658 baseline and the Phase-0 Jev arm
- [`PIPELINE_TERMINOLOGY.md`](../technical/PIPELINE_TERMINOLOGY.md) — phase vocabulary
