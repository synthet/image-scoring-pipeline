---
type: Feature Spec
title: ONNX conversion feasibility
description: Feasibility, pros/cons, and phased implementation plan for exporting the backend's scoring and auxiliary models to ONNX.
resource: docs/planning/models/ONNX_CONVERSION_FEASIBILITY.md
tags: [planning, models, onnx, inference]
timestamp: 2026-10-05T00:00:00Z
okf_version: 0.2
---

# ONNX conversion feasibility

Can the models the backend runs in WSL / Docker `gpu-shell` be converted to ONNX, what would it buy us, and how would we do it safely.

**Status:** Research / proposal — no code changes. Tracked in [#404](https://github.com/synthet/image-scoring-pipeline/issues/404); each implementation phase gets its own issue.
**Related:** [WINDOWS_NATIVE_WEBUI_PLAN.md](../setup/WINDOWS_NATIVE_WEBUI_PLAN.md), [IQA_MODEL_STACK_UPDATE_PROPOSAL.md](IQA_MODEL_STACK_UPDATE_PROPOSAL.md), [MODELS_SUMMARY.md](../../technical/MODELS_SUMMARY.md)

## TL;DR
- **Yes for most models, but “PyTorch” does not guarantee a successful export.** The student scorer, bird YOLO, CLIP and MobileNetV2 are the strongest first candidates. TOPIQ and ARNIQA are likely exportable after isolating their tensor-only networks. LIQE needs a custom wrapper and parity work. PyTorch's exporter only covers operators it can lower to ONNX, so each artifact still needs an export smoke test and numerical validation.
- **MUSIQ (TensorFlow) is the hard one.** It is also a production model (SPAQ and AVA), so a fully ONNX, WSL-free scorer depends on either:
  - porting MUSIQ with significant effort, or
  - replacing it with the distilled **student scorer**. The student already predicts proxies for spaq, ava, liqe, topiq, arniqa and the composites (`modules/student_scoring.py` `TEACHER_PROXY_KEYS`).
- **The main risk is score drift, not producing a file.** Fusion uses fixed percentile anchors calibrated on about 61k already-scored images, so any ONNX path must match the current scores almost exactly.
- **For new Windows work, prefer CUDA EP on the target NVIDIA laptop and benchmark WinML as the vendor-neutral fallback.** ONNX Runtime now describes DirectML as sustained engineering and recommends WinML for new Windows projects. A Python integration can still use `onnxruntime-gpu` (CUDA) or `onnxruntime-directml`, but they are separate deployment choices rather than one universal wheel.

## What “can be converted” means

This report uses four different outcomes; they must not be collapsed into a single yes/no:

1. **Exportable:** a tool can produce a syntactically valid ONNX graph.
2. **Runnable:** ONNX Runtime can load every node on the selected Windows execution provider, with intentional CPU fallback if needed.
3. **Equivalent:** preprocessing, outputs and ranking pass the parity gates below.
4. **Replaceable:** the ONNX artifact can take over the production model without recalibrating fusion, embeddings or thresholds.

Only an observed parity run can establish outcomes 3 and 4. The classifications below are therefore engineering estimates, not claims that the repository already contains validated exports.

## Feasibility by model

| Model | Status | Code | Framework / input | Conversion verdict |
|---|---|---|---|---|
| **MUSIQ SPAQ, AVA** | production | `scripts/python/run_all_musiq_models.py` (`MultiModelMUSIQ`), `modules/engines/musiq_model.py` | TF Hub / Kaggle SavedModel; `.npz` fallback in `models/checkpoints/` | **Red / research.** The graph accepts encoded bytes, decodes them, constructs a variable multi-scale patch pyramid and applies hashed 2-D position embeddings. `tf2onnx` can convert SavedModels, but its own documentation warns that TensorFlow has more operators than ONNX and not every model converts correctly. Move byte decoding and patch construction into versioned native preprocessing, then attempt export of the numeric core. Do not schedule this as a one-command conversion. |
| **LIQE** | production | `modules/liqe.py` (pyiqa `liqe`) | PyTorch CLIP ViT-B/32 + fixed prompt ensemble; aspect-preserving resize | **Amber / custom export.** Export a tensor-only wrapper around the image encoder and IQA aggregation; precompute immutable text features when their exact equivalence is proved. Patch sampling and variable geometry are the likely blockers. Test fixed-shape first, then decide whether dynamic H/W is worth the provider risk. |
| **TOPIQ-NR** | production | `modules/topiq.py` (pyiqa `topiq_nr`) | PyTorch ResNet50 + attention; aspect-preserving resize | **Amber-green / likely.** Isolate `metric.net`, keep PIL resize outside the graph, and export the tensor network with the current PyTorch Dynamo exporter. Start with representative fixed shapes; dynamic H/W remains a separate acceptance test. Verify whether pyiqa normalization wraps the net rather than assuming it is captured. |
| **ARNIQA** | production | `modules/arniqa.py` (pyiqa `arniqa`) | PyTorch ResNet50 + dataset-specific regressor; internal half-scale branch | **Amber-green / likely.** Export the selected head and both scale paths in one wrapper. The active head is part of artifact identity. Preserve the internal interpolation mode and compare each configured head separately. |
| **Student scorer** | shadow | `modules/student_scoring.py` | PyTorch `convnext_tiny`, fixed 512×512, multi-head | **Green / best pilot.** ConvNeXt is directly supported by Hugging Face Optimum, while this custom multi-head module can use `torch.onnx.export`. Fixed input and one tensor forward make it the lowest-risk end-to-end pilot. |
| **Bird detector** | auxiliary | `modules/bird_detection.py` | Ultralytics YOLO, fixed `imgsz=640` policy | **Green / built-in exporter.** Ultralytics documents `model.export(format="onnx")`. Keep letterbox, NMS, coordinate scaling and the repository's deterministic box ranking outside the graph unless explicitly exported and parity-tested. Export support does not make the result “trivial.” |
| **RTMDet fallback** | auxiliary, already ONNX | `modules/detectors/rtmdet.py` | ONNX Runtime | **Already converted.** This is the best local pattern for manifest hashes, provider-unavailable errors and preprocessing parity; no export work is required. |
| **CLIP ViT-B/32** | production auxiliary | `modules/tagging.py`, `modules/embedding_extractors.py`, `modules/similar_search.py`, `modules/clip_accessibility.py` | Hugging Face Transformers | **Green / officially supported.** Optimum has a zero-shot image-classification ORT class that explicitly supports CLIP. Export image and text towers with named outputs. Any changed image vector requires a new embedding-space version or a complete re-embed; do not silently overwrite `clip_vit_b32_image`. |
| **BLIP captioning** | production auxiliary | `modules/tagging.py` | Hugging Face encoder-decoder plus autoregressive `generate()` | **Amber-red / prototype only.** Current Optimum ONNX supported-architecture material does not list BLIP explicitly. A custom vision-encoder/decoder export may be possible, but generation needs a host-side token loop and usually decoder-with-past graphs. Keep PyTorch as the supported path until a real checkpoint export passes caption parity. |
| **BioCLIP 2** | production auxiliary | `modules/bird_species.py` | OpenCLIP-compatible image/text towers | **Amber / custom export.** The tensor towers are CLIP-like, but the repository does not load this checkpoint through the supported Hugging Face `CLIPModel` path. Export the exact OpenCLIP implementation or migrate only after class-logit parity, taxonomy and preprocessing fingerprints match. |
| **MobileNetV2 culling** | production | `modules/embedding_extractors.py`, `modules/culling_embeddings.py` | torchvision MobileNetV2 GAP embedding | **Green / easy.** Fixed tensor input and a standard CNN are low risk. Stored embeddings define stack geometry, so changing numerics means a new embedding-space version, threshold re-tuning and backfill. |
| **QPT-V2** | disabled / WIP | `modules/qpt_v2.py`, `modules/qpt_v2_arch.py` | custom PyTorch HiViT-T reconstruction | **Amber-red / defer.** It is probably graph-exportable, but its native inference recipe and score range are not validated. ONNX would only add a second unknown; validate the PyTorch model first. |
| **DINOv2** | roadmap | not production yet | Hugging Face Transformers / timm | **Green for a standard HF checkpoint.** Optimum lists DINOv2. Export only after the checkpoint, pooling and preprocessing contract is selected; then version the embedding space. |
| **SigLIP2** | roadmap | not production yet | Hugging Face Transformers | **Amber-green.** Optimum lists SigLIP, but its public support list does not independently prove every SigLIP2 checkpoint/task. Query `TasksManager` for the exact `model_type`, then run a checkpoint export before selecting it as the Windows backend. |
| **RAM++ / OpenCLIP L/14 / LAION aesthetic head** | optional roadmap | not production yet | custom/open_clip PyTorch | **Amber.** The component operators are conventional, but these are not the same as an officially supported HF `CLIPModel` export. Use a custom wrapper, lock preprocessing and export the aesthetic MLP with its exact parent embedding. |

No general ONNX export/runtime tooling is declared in the core requirements today. The RTMDet provider imports `onnxruntime` optionally and fails closed when it is absent; `tf2onnx` and Optimum are not project dependencies.

## Windows-native runtime decision

| Target | Package / API | Recommendation for this project |
|---|---|---|
| NVIDIA RTX 4060 laptop, Python backend | `onnxruntime-gpu` with `CUDAExecutionProvider`, then `CPUExecutionProvider` | **Primary benchmark target.** Pin an ORT version compatible with the installed CUDA/cuDNN major versions. ORT documents `preload_dlls()` for resolving the DLLs bundled with PyTorch or NVIDIA site packages on Windows. |
| Mixed-vendor Windows Python | `onnxruntime-directml` | **Compatibility experiment, not the default.** DirectML is broadly available but is in sustained-engineering mode. Preserve the existing global serialization/opt-out lessons and benchmark every graph. |
| Future packaged Windows application | WinML (`Microsoft.AI.MachineLearning`) | **Preferred new Windows API according to ONNX Runtime.** It can dynamically select execution providers, but adopting it from this Python backend would require an integration boundary (native helper, service or gallery-side implementation); it is not a drop-in Python backend change. |
| CPU fallback | `onnxruntime` / `CPUExecutionProvider` | **Required correctness fallback and CI baseline.** It proves graph portability, not acceptable production throughput. |

Do not install multiple mutually competing ORT Python distributions into the same production environment. Build separate locked Windows environment profiles for CUDA, DirectML and CPU, and have diagnostics record `ort.__version__`, available providers, selected provider and fallback nodes.

## Recommended conversion order

1. **Student scorer:** proves custom PyTorch export, multi-output wiring and the parity harness without changing production.
2. **MobileNetV2:** proves embedding-space comparison and Windows batch throughput.
3. **CLIP ViT-B/32:** uses an officially supported Optimum route; initially shadow-write to a new embedding-space ID.
4. **Bird YOLO:** use Ultralytics' exporter and compare pre-NMS tensors plus final repository-ranked boxes.
5. **TOPIQ, then ARNIQA:** tensor-only wrappers, externalized current PIL preprocessing, production score parity.
6. **LIQE and BioCLIP 2:** custom dual-tower/prompt exports after simpler CLIP establishes the harness.
7. **BLIP:** only if removing PyTorch from the keywords phase is still valuable after measurements.
8. **MUSIQ:** last, or avoid it by validating and promoting the student replacement with new calibration.

This sequence answers the Windows question with evidence early: a successful student export alone is not enough; a production decision needs at least one scorer, one embedding model and one detector measured on the actual Windows target.

## Pros
- **Windows-native inference, no WSL/Docker needed.** ONNX Runtime runs on Windows with the CUDA or DirectML execution providers. This removes the `gpu-shell` / `~/.venvs/tf` dependency for scoring and matches the existing `run_webui_windows.bat` path.
- **One runtime instead of TF + PyTorch.** Today MUSIQ needs TensorFlow and the rest need torch + pyiqa. ONNX removes the TF/torch GPU memory contention on 8 GB cards.
- **Smaller, stable deployment.** No pyiqa, TF Hub or Kaggle downloads at runtime, and pinned `.onnx` artifacts.
- **Potential speed improvement.** ORT graph optimizations, provider-specific kernels, TensorRT or FP16 may improve throughput, but there is no trustworthy project-specific multiplier until the same preprocessing and batch sizes are benchmarked on the target Windows machine.
- **Portability to the gallery.** `onnxruntime-node` could in principle run light models, such as the student model or CLIP, inside Electron.

## Cons and risks
- **Score parity.** Resize and interpolation, normalization, patch sampling and FP16 can each shift scores. Even small shifts move percentile-normalized composites and star ratings for the existing 61k images. Parity gates are mandatory, or the whole library needs a re-score and recalibration.
- **MUSIQ effort.** It is the hardest model and sits in the production fusion. Without it, a full move off WSL is impossible unless the student model (or another model) replaces it in fusion.
- **Dynamic shapes.** The IQA models deliberately keep the aspect ratio (`max_dimension` resize). Dynamic H/W exports can be slower or hit unsupported ops. Fixed-size exports change the model's behaviour.
- **Two code paths to maintain** during the transition: the torch/TF wrappers and the ONNX wrappers.
- **Licensing and redistribution.** Check each weight license before shipping `.onnx` files. For example, ARNIQA is Apache-2.0 and MUSIQ is Apache-2.0; the others are unconfirmed.
- **DirectML numerics** can differ slightly from CUDA, so parity must be checked per execution provider.

## Parity lessons from an exact-reimplementation experiment

A separate research exercise rebuilt a complete ONNX-based scoring pipeline, and drove it from about
50% to 100% bit-exact agreement with a reference run on 436 frames. Every step below moved scores by
several points until it was fixed. The same lessons apply to spec 03 (RTMDet on ONNX) and to any
IQA export here.

1. **Resize fit is part of the model input.**
   - "Fit inside", "cover" and "letterbox" use **one scale for both axes**; only an explicit "fill"
     stretches the axes independently.
   - Mixing them up misaligns every box and keypoint.
   - Record the fit and the target size in the rendition or crop policy.
2. **The resampler library is part of identity.** PIL, libvips and OpenCV produce different pixels
   for the same nominal Lanczos resize, which is enough to change sharpness measures. Record the
   library and its version.
3. **Normalize inputs in float64, then cast to float32.** This gave bit-identical embeddings across
   runs; float32 normalization did not.
4. **Pin the onnxruntime version.**
   - Runtime versions moved results.
   - In that exercise, CPU vs DirectML made no measurable difference. Still check parity per
     execution provider, as above.
5. **Allow a per-model execution-provider opt-out.** Large CLIP graphs were unreliable on DirectML.
6. **Serialize every DirectML session in a process through one global lock.** Concurrent
   DirectML sessions crashed.
7. **Version-stamp derived caches.**
   - Bump an extractor or embedding version whenever preprocessing changes.
   - Drop dependent caches on the bump. A stale embedding cache once produced false regressions.
8. **Keep a trace switch.**
   - An environment flag should dump every intermediate per frame as JSON, for diffing against a
     reference.
   - A one-frame diagnostics bundle (overlays + JSON) makes bug reports reproducible.

These lessons turn "parity gates are mandatory" (above) into a concrete checklist for
`scripts/onnx/parity_check.py`.

## Implementation plan (phased, each phase gated by parity)

**Phase 0: tooling and harness**
- Add optional deps (`onnx`, `onnxruntime-gpu`, `onnxscript`) behind an extra, not core requirements.
- Create `scripts/onnx/parity_check.py`:
  - Given a model name and an ONNX file, score N images (default 200, sampled from the DB) with both the existing `IScoringModel` wrapper (`modules/engines/*`) and ORT.
  - Report max |Δ|, mean |Δ|, Spearman ρ and the percentile-normalized Δ.
  - Pass gate: ρ ≥ 0.999 and normalized |Δ| ≤ 0.005 (proposed; adjust after the pilot).

**Phase 1: pilot (student + MobileNetV2)**
- Create `scripts/onnx/export_student.py`: load via `StudentScorerService.load_bundle`, then `torch.onnx.export` at fixed 512 with opset 17.
- Export the MobileNetV2 feature extractor with the repository's exact fixed preprocessing contract.
- Run the parity check for both on CPU and the chosen Windows GPU provider, and record the results in `docs/reports/`.

**Phase 2: runtime integration**
- Add `modules/engines/onnx_model.py`, an `IScoringModel` subclass with `framework = "onnx"`. It holds an ORT session and reuses the existing preprocessing and `score_range`.
- Register it in `modules/engines/factory.py` behind a config switch such as `scoring.models.<name>.backend: "onnx"`.
  - That config key does **not exist yet**. It would be new, so it must be documented in `config.example.json` and `docs/CANONICAL_SOURCES.md` per the repo's no-invent rule.
- Run it in shadow first, with the existing shadow mechanism.

**Phase 3: supported and custom PyTorch models**
- CLIP via Optimum and bird YOLO via its built-in exporter.
- TOPIQ and ARNIQA through tensor-only wrappers; start fixed-shape and add dynamic-shape artifacts only if measurements justify them.
- LIQE and BioCLIP 2 after CLIP parity; precompute text features only if the resulting logits are equivalent.

**Phase 4: MUSIQ decision.** Pick one:
- **(a)** Port the preprocessing to NumPy and export the core via tf2onnx or jax2tf, then run the parity check.
- **(b)** Keep MUSIQ on TF in `gpu-shell`, with ONNX for everything else.
- **(c)** Promote the ONNX student model to replace the SPAQ/AVA inputs in fusion. This needs recalibration.

  Recommendation: evaluate (c) first. It is the cheapest route to WSL-free scoring.

**Process:** file a GitHub issue per phase on `synthet/image-scoring-pipeline` and add it to the Project board before starting it (no work without an issue).

## Primary references checked (2026-10-05)

- [Hugging Face Optimum: export a model to ONNX](https://huggingface.co/docs/optimum-onnx/onnx/usage_guides/export_a_model) — supported-task discovery with `TasksManager`, custom configs, validation, dynamic axes and current exporter selection.
- [Hugging Face Optimum: ONNX Runtime model classes](https://huggingface.co/docs/optimum-onnx/onnxruntime/package_reference/modeling_ort) — official CLIP support for zero-shot image classification.
- [Hugging Face Optimum: ONNX architecture overview](https://huggingface.co/docs/optimum-onnx/onnx/overview) — architecture support used for ConvNeXt, DINOv2, MobileNetV2, SigLIP and CLIP estimates. Exact checkpoint/task support must still be queried.
- [PyTorch: export a model to ONNX](https://docs.pytorch.org/tutorials/beginner/onnx/export_simple_model_to_onnx_tutorial.html) — Dynamo-based `torch.onnx.export` is the recommended modern path; `onnx` and `onnxscript` are required.
- [Ultralytics: model export](https://docs.ultralytics.com/modes/export/) — documented `format="onnx"` route for YOLO.
- [ONNX Runtime: install matrix](https://onnxruntime.ai/docs/install/) and [CUDA execution provider](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html) — Windows packages, CUDA/cuDNN compatibility and DLL preloading.
- [ONNX Runtime: Windows](https://onnxruntime.ai/docs/get-started/with-windows.html) and [DirectML provider](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html) — WinML recommendation and DirectML sustained-engineering status.
- [`tf2onnx` project README](https://github.com/onnx/tensorflow-onnx/blob/main/README.md) — supported input formats/opsets and the explicit warning that TensorFlow-to-ONNX operator coverage is incomplete.
