---
type: Report
title: Scoring loop ordering (image-major vs model-major)
description: Should the scoring phase run every model per image, or one model over all images? Code review, measured costs, and a recommendation (micro-batched image-major), reconciled with an external generic analysis.
resource: docs/reports/scoring-loop-ordering-2026-10-05.md
tags: [reports, research, scoring, gpu, batching, performance]
timestamp: 2026-10-05T00:00:00Z
okf_version: 0.2
---

# Scoring loop ordering: image-major vs model-major

**Question:** for the multi-model scoring pipeline (MUSIQ SPAQ/AVA, LIQE, TOPIQ, ARNIQA, about 61k photos, many of them 20–45 MP NEF, one 8 GB GPU), which ordering is better?
- **Image-major:** loop over images, and run every model on each one.
- **Model-major:** load one model, run it over all images, then move to the next model.

**Answer:** neither pure form. Keep image-major ordering with all models resident, but feed the GPU a **micro-batch of N prepared images**. Inside the chunk, models are the outer loop and images the inner loop. Each image's complete result then goes to the unchanged `ResultWorker`.

Do not move the scoring phase to model-major. It frees no VRAM, saves no meaningful load time, multiplies RAW decoding unless decodes are cached, and breaks the resume and XMP contracts.

**Decode matters more than ordering.** A NEF decode costs about 3× the whole five-model ensemble.

*Method:* static code review of `master` (2026-10-05), the repo's existing measurements, and published framework guidance (sources below). No new benchmarks were run. Figures marked *est.* are arithmetic on the cited numbers.

## How scoring runs today

- **One thread per stage.** `PrepWorker` (CPU) → `ScoringWorker` (GPU) → `ResultWorker` (DB/XMP), joined by bounded queues ([engine.py](../../modules/engine.py#L182)). The scoring architecture doc states it: one image per model call, no tensor-level batching ([scoring.md](../architecture/pipeline/phases/scoring.md)).
- **Image-major, one image per call.** `ScoringWorker.process` ([pipeline.py](../../modules/pipeline.py#L493)) preprocesses the image, calls `torch.cuda.empty_cache()`, then `MultiModelHost.run_all_models` ([host.py](../../modules/engines/host.py#L84)). That loops `for model in active: model.predict(path)`, in registry order TOPIQ → ARNIQA → SPAQ → AVA → LIQE. `IScoringModel` has no batch method, the pyiqa wrappers `unsqueeze(0)`, and MUSIQ sends one encoded JPEG per TF Hub call.
- **Models load once and stay loaded.** `load_enabled_and_shadow` ([host.py](../../modules/engines/host.py#L72)) loads every active model at the first scoring job, and nothing unloads them. TF runs with memory growth enabled.
- **All models share one input.** With the default config (no `scoring.model_preprocessing`), every model reads the same 512 px letterboxed JPEG ([pipeline.py](../../modules/pipeline.py#L520)). Every pyiqa input is therefore already `3×512×512`, so batching needs no aspect-ratio bucketing.
  - Side effect: LIQE/TOPIQ/ARNIQA `max_dimension` never triggers.
  - `preprocess_image` runs on the **GPU thread**, so it serializes with inference.
- **Across phases the pipeline is already model-family-major.** `PipelineOrchestrator` runs one phase over the whole folder before the next ([pipeline_orchestrator.py](../../modules/pipeline_orchestrator.py)). Inside each phase the loop is image-major, and no phase unloads its models.

## Costs that decide it

| Quantity | Value | Source |
|---|---|---|
| Five-model ensemble, `predict()` mean, RTX 4060 Laptop | **179.5 ms/image**: SPAQ 42.6, AVA 37.8, TOPIQ 37.4, LIQE 33.1, ARNIQA 28.6 | [model-selection-findings-2026-10-02](model-selection-findings-2026-10-02.md) (#494) |
| RAW decode (`open_rendition_for_ml` + RGB + orientation) | **507 ms p50**, 774 ms p95 | [07-blockers-and-decisions](../specs/pipeline-streamlining/07-blockers-and-decisions.md) (#377) |
| Decodes per RAW across phases today | 3 (4 for bird frames) | same |
| Cached 2048 px rendition read | 0.021 s p50 (about 22× faster than decoding) | [01-rendition](../specs/pipeline-streamlining/01-rendition.md) |
| pyiqa peak GPU memory (1080×800, V100) | MUSIQ 0.41, LIQE 0.96, TOPIQ-NR 0.67, ARNIQA 0.33 GB | [pyiqa Efficiency_benchmark.csv](https://github.com/chaofengc/IQA-PyTorch/blob/main/tests/Efficiency_benchmark.csv) |
| Batching gain, ResNet-50 class, bs 1 → 16 | about 4× throughput (T4, not this card) | [NVIDIA NGC ResNet-50](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/dle/resources/resnet_pyt/performance) |

Over 61k images:
- **Inference:** 61k × 0.18 s ≈ **3 GPU-hours** at bs=1.
- **Decoding, one pass:** 61k × 0.5 s ≈ **8.5 CPU-hours**. Today's 3–4 decodes per RAW put it at **25–34 h** (*est.*).
- **Model loading:** even a pessimistic 60 s cold load is under 0.1% of the run, whichever ordering is used (*est.*).

## Why not model-major for scoring

| Dimension | Image-major today (bs=1) | Model-major (whole library) | **Recommended: resident models, micro-batch of N** |
|---|---|---|---|
| GPU throughput | 5 bs-1 calls per image | Large batches | Same batching gain once N ≥ 16–32 |
| VRAM | All 5 resident, about 3 GB (*est.*) | No gain in-process: TF never returns MUSIQ's memory ([TF GPU guide](https://www.tensorflow.org/guide/gpu)) | All 5 resident plus N × 512² activations |
| Decoding | Once per image | Once per model unless renditions are cached | Once per image |
| Resume | Per image; matches the skip check | **Breaks** it (see below) | Unchanged |
| XMP / fusion | Written once, final | Partial fusion rewrites ratings later | Unchanged |
| Latency to a complete result | One image | Hours | One chunk (seconds) |

The resume problem is concrete. `is_image_scoring_complete` ([db_legacy.py](../../modules/db_legacy.py#L7938)) treats an image as done when **any one** of spaq/ava/liqe/paq2piq/koniq has a positive score. Suppose a model-major run saved SPAQ for every image and then stopped. A non-forced rerun would skip all of them, and they would never get the other four models.

Fusion re-weights over the models present ([score_normalization.py](../../modules/score_normalization.py#L179)). Fusing early would therefore write one star rating to XMP now and a different one later.

## Recommendation (ordered by payoff)

1. **Decode once and prepare in parallel.**
   - Run more than one prep worker, reading the shared rendition cache ([01-rendition](../specs/pipeline-streamlining/01-rendition.md)) instead of re-converting each RAW.
   - Move `preprocess_image` off the GPU thread into `PrepWorker`.
2. **Micro-batch in `ScoringWorker`.**
   - Drain up to N jobs from the queue, which must hold at least N, with a short flush timeout.
   - Call `empty_cache` per chunk or at phase end instead of per image.
   - Start with N ≈ 16 and use a fixed N, because changing batch sizes fragment PyTorch's caching allocator.
3. **Add `MultiModelHost.run_all_models_batch(paths)`.** Models outer, images inner, returning today's per-image result shape. `ResultWorker`, fusion, XMP and the resume check stay as they are.
4. **Add an optional `IScoringModel.predict_batch`.** The default loops over `predict`. The pyiqa models stack tensors. If a batch raises, retry it image by image so one bad file fails alone.
5. **MUSIQ stays at bs=1 for now.**
   - Change that only if `saved_model_cli show --all` shows its signature accepts a batch of inputs.
   - A PyTorch or ONNX MUSIQ ([ONNX_CONVERSION_FEASIBILITY.md](../planning/models/ONNX_CONVERSION_FEASIBILITY.md)) also removes TF's unreleasable memory pool.
6. **Unload models at phase boundaries.**
   - Add `unload()` to the scoring models; `embedding_extractors.unload()` is the precedent.
   - Call it between orchestrated phases, so scoring, keywords and species models are not all resident at once (about 5.5–6 GB of weights, *est.*). The streamlining spec already targets one phase's models at a time.
7. **Later:** add a batch endpoint to the remote GPU runner (`/v1/scoring/run_all_models` is single-file today), and update [scoring.md](../architecture/pipeline/phases/scoring.md).

**Where model-major does fit:**
- **Backfilling one new model** across an already-scored library. Run it as a model-major pass over cached renditions. This needs a per-(image, model) completeness check against `image_model_scores` and a final re-fusion, not today's any-model check.
- **A model too large to share 8 GB with the ensemble.** Q-Align peaks at 15.4 GB in fp16 and 5.0 GB at 4-bit (pyiqa benchmark).

## Reconciling the external generic analysis

The owner supplied a framework-level comparison: "Optimizing Multi-Model GPU Inference: An Analytical Comparison". It contains no project data, and its throughput table is labelled illustrative.

**Where it agrees:**
- Its "batched image groups" hybrid is the recommendation above.
- Load cost matters only when N is small.
- Its implementation practices are sound: parallel data loading, pinned memory with `non_blocking` copies, `torch.no_grad()`, and measuring first.

**Where it does not transfer:**
- **Memory.** It assumes model-major saves memory because only one model is resident. Here all five fit, and its `del model; torch.cuda.empty_cache()` pattern cannot free TF's memory for MUSIQ.
- **Decoding.** Its time models leave out I/O and preprocessing as overlappable. Here decoding is the largest cost, and model-major without a decode cache multiplies it.
- **Correctness.** It does not consider resume semantics or XMP rating churn, which rule out model-major here.
- **Its decision chart.** Applied to this pipeline it says: models fit → latency not critical → model-major. That only holds if model-major were the sole way to batch, which it is not.
- **Smaller errors:**
  - Its ONNX snippet calls a nonexistent `ort.keras.backend.clear_session()`, and `cuda.empty_cache()` does not apply to ONNX Runtime.
  - "Activations are 5–10% of weights" is an LLM rule of thumb, not a CNN/ViT figure at 512 px with a batch.
  - Its "latency ≈ T_B/M" understates model-major latency, which is close to the full run for most images.

**Worth adopting from it:**
- **Background-loading the next phase's models** once phase-boundary unloading exists (item 6).
- **The break-even ratio** Σt_load / (N·Σt_infer) as the one-line argument that load cost is negligible here (about 60 s against about 3 h).
- **Its benchmark checklist**, which matches the measurements below.

## Measurements still needed

Several belong to #416 (per-model peak VRAM).

1. **Per-stage timing of the scoring path on NEFs:** `convert_raw_to_jpeg`, the exiftool safety check, `preprocess_image`, each `predict`, and `empty_cache`, with GPU utilization sampled alongside. If the GPU thread is starved, items 1–2 outrank batching.
2. **Peak VRAM with all five scoring models loaded,** then again after the keyword and species models load in the same process.
3. **Batch-size sweep** (1, 4, 8, 16, 32) for LIQE/TOPIQ/ARNIQA at 3×512×512 on the 4060 Laptop.
4. **Parity of batched vs bs=1 scores.** LIQE samples patches internally, and any drift requires a `SCORING_EXECUTOR_VERSION` bump.
5. **MUSIQ SavedModel signature:** can it batch at all?
6. **Cold load and first-inference warm-up per model,** to cost phase-boundary unloading.

## Sources

- **Code (master, 2026-10-05):**
  - [engine.py](../../modules/engine.py), [pipeline.py](../../modules/pipeline.py), [host.py](../../modules/engines/host.py), [db_legacy.py](../../modules/db_legacy.py#L7938), [score_normalization.py](../../modules/score_normalization.py)
  - [pipeline_orchestrator.py](../../modules/pipeline_orchestrator.py), [embedding_extractors.py](../../modules/embedding_extractors.py), [remote_gpu/runtime.py](../../modules/remote_gpu/runtime.py)
- **Repo measurements and specs:**
  - [model-selection-findings-2026-10-02](model-selection-findings-2026-10-02.md)
  - [pipeline-streamlining 01-rendition](../specs/pipeline-streamlining/01-rendition.md) and [07-blockers-and-decisions](../specs/pipeline-streamlining/07-blockers-and-decisions.md)
- **External:**
  - [pyiqa efficiency benchmark](https://github.com/chaofengc/IQA-PyTorch/blob/main/tests/Efficiency_benchmark.csv)
  - [TensorFlow GPU guide](https://www.tensorflow.org/guide/gpu) and [PyTorch CUDA semantics](https://pytorch.org/docs/stable/notes/cuda.html)
  - [Ray Data batch inference](https://docs.ray.io/en/latest/data/batch_inference.html): resident models, CPU preprocessing overlapped with GPU stages
  - [NVIDIA Triton ensembles](https://github.com/triton-inference-server/server/blob/main/docs/user_guide/ensemble_models.md)
  - [img2dataset](https://github.com/rom1504/img2dataset): resize once, then run model passes over the materialized set
  - [NVIDIA NGC ResNet-50 performance](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/dle/resources/resnet_pyt/performance)
