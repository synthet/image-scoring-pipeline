---
type: Feature Spec
title: ONNX conversion feasibility
description: Feasibility, pros/cons, and phased implementation plan for exporting the backend's scoring and auxiliary models to ONNX.
resource: docs/planning/models/ONNX_CONVERSION_FEASIBILITY.md
tags: [planning, models, onnx, inference]
timestamp: 2026-09-24T00:00:00Z
okf_version: 0.1
---

# ONNX conversion feasibility

Can the models the backend runs in WSL / Docker `gpu-shell` be converted to ONNX, what would it buy us, and how would we do it safely.

**Status:** Research / proposal — no code changes. Tracked in [#404](https://github.com/synthet/image-scoring-backend/issues/404); each implementation phase gets its own issue.
**Related:** [WINDOWS_NATIVE_WEBUI_PLAN.md](../setup/WINDOWS_NATIVE_WEBUI_PLAN.md), [IQA_MODEL_STACK_UPDATE_PROPOSAL.md](IQA_MODEL_STACK_UPDATE_PROPOSAL.md), [MODELS_SUMMARY.md](../../technical/MODELS_SUMMARY.md)

## TL;DR
- **Yes for most models.** Every PyTorch model can be exported: TOPIQ, ARNIQA, LIQE, the student scorer, YOLO and CLIP.
- **MUSIQ (TensorFlow) is the hard one.** It is also a production model (SPAQ and AVA), so a fully ONNX, WSL-free scorer depends on either:
  - porting MUSIQ with significant effort, or
  - replacing it with the distilled **student scorer**. The student already predicts proxies for spaq, ava, liqe, topiq, arniqa and the composites (`modules/student_scoring.py` `TEACHER_PROXY_KEYS`).
- **The main risk is score drift, not conversion.** Fusion uses fixed percentile anchors calibrated on about 61k already-scored images, so any ONNX path must match the current scores almost exactly.

## Feasibility by model

| Model | Status | Code | Framework / input | ONNX feasibility |
|---|---|---|---|---|
| **MUSIQ SPAQ, AVA** | production | `scripts/python/run_all_musiq_models.py` (`MultiModelMUSIQ`), `modules/engines/musiq_model.py` | TF Hub / Kaggle SavedModel; `.npz` fallback in `models/checkpoints/` | **Hard.** The graph takes encoded image bytes, then decodes, builds a multi-scale patch pyramid and applies hash-based 2D position embeddings in-graph. Patch count varies with image size. tf2onnx does not cleanly handle DecodeJpeg or the patching ops. A realistic route is to port the preprocessing to NumPy and export only the transformer core. That core would come from the SavedModel via tf2onnx, or from the `.npz` (JAX/Flax) via jax2tf → tf2onnx. Expect several days of work plus parity debugging. |
| **LIQE** | production | `modules/liqe.py` (pyiqa `liqe`) | PyTorch CLIP ViT-B/32 + text prompts; aspect-preserving resize to `max_dimension` | **Medium.** The text embeddings for the prompt set are constant, so precompute them and export only the image tower plus patch sampling. Variable input size needs dynamic axes, or the patch unfold is moved outside the graph. |
| **TOPIQ-NR** | production | `modules/topiq.py` (pyiqa `topiq_nr`) | PyTorch ResNet50 + attention; aspect-preserving resize | **Medium-easy.** `torch.onnx.export(metric.net, dynamic_axes={H,W})`. Normalization lives inside pyiqa, so check it is captured. |
| **ARNIQA** | production | `modules/arniqa.py` (pyiqa `arniqa`) | PyTorch ResNet50 + regressor; the model downscales internally | **Medium-easy.** Same approach as TOPIQ. The internal half-scale input must be inside the graph or replicated outside it. |
| **Student scorer** | shadow | `modules/student_scoring.py` | PyTorch `convnext_tiny`, fixed 512×512, multi-head | **Easy.** Fixed shape, one forward pass. Best pilot. |
| **Bird detector** | aux | `modules/bird_detection.py` | Ultralytics YOLO | **Trivial.** `YOLO(weights).export(format="onnx")`. `image-scoring-model` is canonical for its weights. |
| **CLIP** (tagging, similarity, embeddings) | aux | `modules/tagging.py`, `modules/embedding_extractors.py`, `modules/similar_search.py`, `modules/clip_accessibility.py` | HF transformers | **Easy.** `optimum-cli export onnx`. Embedding outputs must match stored pgvector values, or a re-embed is needed. |
| **BLIP captioning** | aux | `modules/tagging.py` | HF encoder-decoder + `generate()` | **Medium.** Optimum supports it, but the decoding loop is split across several ONNX files. |
| QPT-V2 | disabled (WIP) | `modules/qpt_v2.py` | PyTorch | Out of scope. |

No ONNX tooling is in the repo today: `onnxruntime`, `tf2onnx` and `optimum` are not in the requirements.

## Pros
- **Windows-native inference, no WSL/Docker needed.** ONNX Runtime runs on Windows with the CUDA or DirectML execution providers. This removes the `gpu-shell` / `~/.venvs/tf` dependency for scoring and matches the existing `run_webui_windows.bat` path.
- **One runtime instead of TF + PyTorch.** Today MUSIQ needs TensorFlow and the rest need torch + pyiqa. ONNX removes the TF/torch GPU memory contention on 8 GB cards.
- **Smaller, stable deployment.** No pyiqa, TF Hub or Kaggle downloads at runtime, and pinned `.onnx` artifacts.
- **Speed.** Typically 1.2–2× with ORT and graph optimizations. More with the TensorRT execution provider or FP16, which then needs recalibration checks.
- **Portability to the gallery.** `onnxruntime-node` could in principle run light models, such as the student model or CLIP, inside Electron.

## Cons and risks
- **Score parity.** Resize and interpolation, normalization, patch sampling and FP16 can each shift scores. Even small shifts move percentile-normalized composites and star ratings for the existing 61k images. Parity gates are mandatory, or the whole library needs a re-score and recalibration.
- **MUSIQ effort.** It is the hardest model and sits in the production fusion. Without it, a full move off WSL is impossible unless the student model (or another model) replaces it in fusion.
- **Dynamic shapes.** The IQA models deliberately keep the aspect ratio (`max_dimension` resize). Dynamic H/W exports can be slower or hit unsupported ops. Fixed-size exports change the model's behaviour.
- **Two code paths to maintain** during the transition: the torch/TF wrappers and the ONNX wrappers.
- **Licensing and redistribution.** Check each weight license before shipping `.onnx` files. For example, ARNIQA is Apache-2.0 and MUSIQ is Apache-2.0; the others are unconfirmed.
- **DirectML numerics** can differ slightly from CUDA, so parity must be checked per execution provider.

## Implementation plan (phased, each phase gated by parity)

**Phase 0: tooling and harness**
- Add optional deps (`onnx`, `onnxruntime-gpu`, `onnxscript`) behind an extra, not core requirements.
- Create `scripts/onnx/parity_check.py`:
  - Given a model name and an ONNX file, score N images (default 200, sampled from the DB) with both the existing `IScoringModel` wrapper (`modules/engines/*`) and ORT.
  - Report max |Δ|, mean |Δ|, Spearman ρ and the percentile-normalized Δ.
  - Pass gate: ρ ≥ 0.999 and normalized |Δ| ≤ 0.005 (proposed; adjust after the pilot).

**Phase 1: pilot (student + TOPIQ)**
- Create `scripts/onnx/export_student.py`: load via `StudentScorerService.load_bundle`, then `torch.onnx.export` at fixed 512 with opset 17.
- Create `scripts/onnx/export_pyiqa.py --metric topiq_nr`: export `metric.net` with dynamic H/W, reusing the resize logic from `modules/topiq.py`.
- Run the parity check for both and record the results in `docs/reports/`.

**Phase 2: runtime integration**
- Add `modules/engines/onnx_model.py`, an `IScoringModel` subclass with `framework = "onnx"`. It holds an ORT session and reuses the existing preprocessing and `score_range`.
- Register it in `modules/engines/factory.py` behind a config switch such as `scoring.models.<name>.backend: "onnx"`.
  - That config key does **not exist yet**. It would be new, so it must be documented in `config.example.json` and `docs/CANONICAL_SOURCES.md` per the repo's no-invent rule.
- Run it in shadow first, with the existing shadow mechanism.

**Phase 3: remaining PyTorch models**
- ARNIQA and LIQE: precompute the LIQE text features and handle patch sampling.
- Bird YOLO and CLIP via built-in exporters.

**Phase 4: MUSIQ decision.** Pick one:
- **(a)** Port the preprocessing to NumPy and export the core via tf2onnx or jax2tf, then run the parity check.
- **(b)** Keep MUSIQ on TF in `gpu-shell`, with ONNX for everything else.
- **(c)** Promote the ONNX student model to replace the SPAQ/AVA inputs in fusion. This needs recalibration.

  Recommendation: evaluate (c) first. It is the cheapest route to WSL-free scoring.

**Process:** file a GitHub issue per phase on `synthet/image-scoring-backend` and add it to the Project board before starting it (no work without an issue).
