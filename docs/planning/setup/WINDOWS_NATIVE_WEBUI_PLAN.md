---
type: Plan
title: Windows-native WebUI and inference plan
description: Current state of running the backend natively on Windows (no WSL/Docker), which models can run there and how, and the remaining work.
resource: docs/planning/setup/WINDOWS_NATIVE_WEBUI_PLAN.md
tags: [planning, setup, windows, onnx, inference, gpu-runner]
timestamp: 2026-10-05T00:00:00Z
okf_version: 0.2
---

# Windows-native WebUI and inference plan

Can the backend (WebUI + pipeline phases) run on a Windows host Python without WSL or Docker `gpu-shell`, and which models can run there with a GPU?

**Status:** Plan, refreshed 2026-10-05. The first version (pre-Postgres) targeted a Firebird-based CPU WebUI; its launcher and setup script shipped, but both still assume Firebird. No implementation issue is open yet.
**Related:** [ONNX_CONVERSION_FEASIBILITY.md](../models/ONNX_CONVERSION_FEASIBILITY.md) (#404), [REMOTE_GPU_RUNNER.md](../../guides/REMOTE_GPU_RUNNER.md), [ENVIRONMENTS.md](../../guides/setup/ENVIRONMENTS.md), [wsl-vs-docker-topology.md](../../guides/setup/wsl-vs-docker-topology.md), [PYTHON_VERSION_CAVEATS.md](../../guides/setup/PYTHON_VERSION_CAVEATS.md)

## TL;DR

- **Host side is mostly there.** `run_webui_windows.bat` and `scripts/setup/setup_windows_native.bat` exist. PostgreSQL (`database.engine: "postgres"`, `127.0.0.1:5432`) works from Windows Python through `psycopg2-binary` + `pgvector`, with Postgres from the Compose `db` service or a native install. What remains is removing the Firebird leftovers from the launcher, setup script and README.
- **GPU inference is the real gap, and it is TensorFlow-shaped.** Native Windows TensorFlow is CPU-only after 2.10. Only two models use TF: **MUSIQ SPAQ/AVA** (production scoring) and **MobileNetV2** (culling embeddings). Every other model is PyTorch and can use CUDA natively on Windows today with a CUDA `torch` wheel. No ONNX is needed for that.
- **ONNX adds** a single runtime, pinned artifacts and a vendor-neutral path. Most models rate green or amber in the [ONNX feasibility matrix](../models/ONNX_CONVERSION_FEASIBILITY.md); MUSIQ is red. The RTMDet detector already runs through `onnxruntime`. The ONNX doc's runtime decision applies here:
  - `onnxruntime-gpu` (CUDA EP) is the primary target on NVIDIA.
  - `onnxruntime-directml` is a compatibility experiment only, because DirectML is in sustained engineering.
  - WinML is for a future packaged app, not the Python backend.
- **The shortest route to GPU scoring from a native host needs no conversion.** Run the Windows WebUI as host and route phases to the existing GPU runner via `gpu_runner.phases.*: "remote"`. The runner can be a Docker container on the same PC or on another PC.

## Current state (verified 2026-10-05)

| Piece | State | Evidence |
|---|---|---|
| Launcher | Exists, still Firebird-oriented: adds `Firebird\` to `PATH`, comment says `launch.py` starts Firebird | `run_webui_windows.bat` |
| Setup script | Exists. Steps 5–6 check `Firebird\firebird.exe` / `scoring_history.fdb` and suggest `migrate_to_firebird.py`. Installs CPU `torch`. Says TF 2.15 works on Python 3.10–3.12, which is wrong because 3.12 is unsupported. | `scripts/setup/setup_windows_native.bat` |
| `launch.py` | Always tries `tasklist` + `Firebird\firebird.exe -a` unless `FIREBIRD_USE_LOCAL_PATH` or `DOCKER_CONTAINER` is set. With no `Firebird\`, it logs "Error starting Firebird" and sleeps 2 s, but does not fail. It is not gated on `database.engine`. | `launch.py` (Firebird block before `webui.py` spawn) |
| DB layer | Postgres is primary. The Firebird import in `modules/db_legacy.py` is wrapped in `try/except ImportError`, so it is harmless without `firebird-driver`. | `config.example.json` `database`, `modules/db_legacy.py` |
| `requirements.txt` | `tensorflow-cpu>=2.15.1,<2.16`, `tensorflow-hub`, `kagglehub`, `pyiqa`, `torch`, `torchvision`, `ultralytics`, `psycopg2-binary`, `pgvector`, `alembic`. **Missing** `open_clip_torch`, `timm`, `transformers`: these live only in `requirements/requirements_keyword_extraction.txt`, `requirements_student_scorer.txt` and `requirements_wsl_gpu.txt`. Without them, the culling embedders, BioCLIP species, CLIP keywords and the student scorer cannot load in a Windows `.venv`. | `requirements.txt`, `Dockerfile` (uses `requirements_wsl_gpu.txt`) |
| Python version | TF 2.15 has no Python 3.12 wheels, so the native `.venv` needs Python 3.10 or 3.11 | [PYTHON_VERSION_CAVEATS.md](../../guides/setup/PYTHON_VERSION_CAVEATS.md) |
| README | "Option 3b" still lists Firebird binaries as a prerequisite and "CPU-only TensorFlow" as the only limitation | `README.md` Option 3 / 3b |
| GPU runner | Shipped. A stateless Docker HTTP service runs `scoring`, `keywords`, `culling`, `localization` and `bird_species` inference for a host that keeps every DB/XMP write. The fallback order is remote → `fallback.local_url` (`http://127.0.0.1:7870`) → embedded. | `modules/remote_gpu/`, `docker-compose.gpu-runner.yml`, `config.example.json` `gpu_runner` |
| ONNX | `onnxruntime` is used only by the RTMDet fallback detector. It is imported lazily, defaults to `CPUExecutionProvider`, and the provider is disabled when the package is missing. Not in any requirements file. | `modules/detectors/rtmdet.py` |

## Model inventory

How each model the backend loads can run on a native Windows host. "Native torch" means a CUDA build of PyTorch in the Windows `.venv`.

The ONNX column is the verdict from [ONNX_CONVERSION_FEASIBILITY.md](../models/ONNX_CONVERSION_FEASIBILITY.md), which owns the detail. The verdicts are engineering estimates: none of them is yet *Equivalent* or *Replaceable* in that doc's four-outcome sense, because no parity run exists.

| Model | Role | Code | Framework | Native Windows GPU today | ONNX verdict |
|---|---|---|---|---|---|
| MUSIQ SPAQ, AVA | production scoring | `modules/engines/musiq_model.py`, `scripts/python/run_all_musiq_models.py` | TF Hub / Kaggle SavedModel | **No.** CPU only (`tensorflow-cpu`). | **Red / research.** In-graph decode and patching. |
| TOPIQ-NR | production scoring | `modules/topiq.py` | PyTorch (pyiqa) | Yes, native torch | Amber-green |
| ARNIQA | production scoring | `modules/arniqa.py` | PyTorch (pyiqa) | Yes, native torch | Amber-green (export the active head) |
| LIQE | production scoring | `modules/liqe.py` | PyTorch (pyiqa, CLIP ViT-B/32) | Yes, native torch | Amber (custom wrapper) |
| Student scorer | disabled in `config.example.json` | `modules/student_scoring.py` | PyTorch ConvNeXt-Tiny, 512×512 | Yes, if its extra deps are installed | **Green.** Best pilot; also the candidate MUSIQ replacement. |
| MobileNetV2 | culling embeddings (default space) | `modules/clustering.py` (`ClusteringEngine`) | TF Keras | **No.** CPU only. | **Green** via `tf2onnx`. Removes the second TF dependency. |
| OpenCLIP ViT-L/14 (LAION, OpenAI), DINOv2-base, SigLIP2 | opt-in culling spaces (`embeddings.culling_spaces`) | `modules/culling_embeddings.py` | PyTorch (`open_clip`, `timm`, `transformers`) | Yes, once deps are added | Amber (OpenCLIP), green (DINOv2), amber-green (SigLIP2). New embedding-space version if numerics change. |
| CLIP (keywords, similarity, accessibility) | aux | `modules/tagging.py`, `modules/similar_search.py`, `modules/clip_accessibility.py`, `modules/embedding_extractors.py` | PyTorch (HF) | Yes, once deps are added | **Green** (Optimum) |
| BLIP captioning | aux | `modules/tagging.py` | PyTorch (HF encoder-decoder) | Yes, once deps are added | Amber-red (prototype only) |
| BioCLIP-2 | bird species | `modules/bird_species.py` (`hf-hub:imageomics/bioclip-2`) | PyTorch (`open_clip`) | Yes, once deps are added | Amber (custom OpenCLIP export) |
| YOLO bird detector | localization | `modules/bird_detection.py`; weights canonical in image-scoring-model | Ultralytics | Yes, native torch | **Green** (built-in exporter; NMS and ranking stay outside the graph) |
| Eye-pose YOLO (`synthet/eye-pose-v0`) | shadow keypoints | `modules/keypoints.py` | Ultralytics pose | Yes, native torch | **Green** |
| RTMDet-tiny (COCO) | detector cascade fallback | `modules/detectors/rtmdet.py` | **ONNX already** (exported by image-scoring-model `training/teacher/export_rtmdet_onnx.py`) | Yes, with an ORT GPU package in that environment profile, passing `providers` | Already converted. Reference pattern: SHA-256 manifest check, lazy import, disabled provider on failure. |
| QPT-V2 | disabled (WIP) | `modules/qpt_v2.py` | PyTorch | n/a | Amber-red / defer |

Hosted LLM judges (`claude`, `cursor`) are API calls with no local weights, so they are not affected.

## Options for GPU inference on a Windows host

| Option | What runs where | Conversion work | Score parity | Notes |
|---|---|---|---|---|
| **A. Native host + GPU runner** | WebUI, DB writes and XMP on Windows `.venv`. Model forward pass on the `gpu-runner` container (same PC or another PC). | None | Identical (same model classes on the runner) | Still needs Docker on *some* machine. Works today: set `gpu_runner.enabled`, `url` and `phases.*: "remote"`. Runner config must match the host's (HTTP 409 otherwise). |
| **B. Native torch, TF on CPU** | Everything in the Windows `.venv`. PyTorch models on CUDA, MUSIQ and MobileNetV2 on CPU. | None | Identical | MUSIQ on CPU is the bottleneck. TF and torch share host RAM, not VRAM. |
| **C. Native torch + ONNX for the TF models** | Same as B, but MobileNetV2 (easy) and MUSIQ (hard) run through `onnxruntime-gpu`. | MobileNetV2 easy, MUSIQ hard | Must pass the parity gate in the ONNX doc | Removes TF entirely. |
| **D. Full ONNX** | All models through ONNX Runtime (CUDA EP, or DirectML as an experiment) | All of the ONNX doc's phases | Parity gate per model and per execution provider | The only option that could serve AMD/Intel GPUs from Python. DirectML is in sustained engineering, and WinML needs a non-Python integration boundary. Biggest effort. MUSIQ can instead be replaced by the student scorer (needs recalibration). |

**Recommendation:** fix the host side first (Phase 1), then document **A** as the supported GPU path. A needs no model work and keeps scores bit-compatible. Treat **B** as the no-Docker fallback. Pursue C/D only through the ONNX doc's parity-gated phases. Its first step (student scorer + TOPIQ pilot) also answers the MUSIQ question.

## Implementation plan

### Phase 1: Postgres-era host cleanup (small)
1. `launch.py`: skip the Firebird probe/start unless `database.engine` is `"firebird"`. This is the existing config key; no new key is needed.
2. `run_webui_windows.bat`: drop the `Firebird\` `PATH` entry and the Firebird comment.
3. `scripts/setup/setup_windows_native.bat`:
   - Require Python 3.10–3.11, matching the TF 2.15 wheels.
   - Replace the Firebird and `.fdb` checks with a Postgres reachability check, for example `python scripts/doctor.py`.
   - Print the CUDA `torch` install command next to the CPU default.
4. Dependencies for the Windows `.venv`: either add `open_clip_torch`, `timm` and `transformers` to `requirements.txt`, or have the setup script also install `requirements/requirements_keyword_extraction.txt`. Prefer the setup-script route, because `requirements.txt` is the CPU/CI baseline.
5. README Option 3/3b: replace the Firebird prerequisite with "PostgreSQL + pgvector reachable at `database.postgres`". State which models get a GPU natively (the PyTorch rows above) and which do not (MUSIQ, MobileNetV2).

### Phase 2: document option A
- Add a "Windows-native host" section to [REMOTE_GPU_RUNNER.md](../../guides/REMOTE_GPU_RUNNER.md): host on `.venv`, runner via `docker-compose.gpu-runner.yml`, and `fallback.local_url` for the same-PC runner.
- Update [ENVIRONMENTS.md](../../guides/setup/ENVIRONMENTS.md): the `.venv` row now covers "Windows WebUI host, optionally + GPU runner".
- Add a Windows-native exception to `.cursor/rules/python-wsl-webapp-env.mdc`.

### Phase 3: ONNX (tracked by the ONNX doc)
Follow the ONNX doc's phases 0–4:
1. Parity harness.
2. Student + MobileNetV2 pilot.
3. `onnx_model.py` engine.
4. Remaining models.
5. MUSIQ decision.

Its conversion order is student → MobileNetV2 → CLIP ViT-B/32 → bird YOLO → TOPIQ, ARNIQA → LIQE, BioCLIP-2 → BLIP → MUSIQ. MobileNetV2 second also removes the second TF dependency, which makes option C cheaper.

Windows-specific points:
- Run parity on the actual Windows target, on both CPU EP and the chosen GPU EP.
- Keep separate locked environment profiles for CUDA, DirectML and CPU. Never co-install competing `onnxruntime*` wheels.
- Expose the execution-provider list per model, because large CLIP graphs were unreliable on DirectML. RTMDet already accepts `providers`. Any new config key must be added to `config.example.json` and [CANONICAL_SOURCES.md](../../CANONICAL_SOURCES.md) first.

**Process:** file one GitHub issue per phase on `synthet/image-scoring-pipeline` and add it to the Project board before starting it.

## Verification

1. Fresh Windows machine, Python 3.11: `scripts\setup\setup_windows_native.bat` completes, and `python scripts/doctor.py` reports config, DB and pgvector OK.
2. `run_webui_windows.bat` starts the API on 7860 with no Firebird messages, writes `webui.lock`, and `/ui/` loads.
3. **Option B smoke:** score a small folder locally. TOPIQ, ARNIQA and LIQE report CUDA, and MUSIQ reports CPU.
4. **Option A smoke:** with `gpu_runner.phases.scoring: "remote"`, the same folder scores on the runner, and the scores match a gpu-shell run of the same files.
5. WSL and Docker launchers are unchanged: `run_webui.bat` and `run_webui_docker.bat` behave as before.

## Risks

| Risk | Mitigation |
|---|---|
| Native-Windows scores drift from gpu-shell scores (different torch/CUDA builds, PIL/libjpeg) | Run the ONNX doc's parity check (ρ, normalized Δ) on a sample before mixing native and container scores in one library |
| Host and runner disagree on config | The runner already rejects mismatched phase config (HTTP 409). Copy `config.json` to the runner. |
| TF and torch in one `.venv` (version pins, DLL conflicts) | Keep TF on CPU (`tensorflow-cpu`). Option C/D removes TF entirely. |
| DirectML instability on large graphs; DirectML in sustained engineering | CUDA EP is the primary target. DirectML gets a per-model opt-out (ONNX doc, lesson 5) and one global lock per process for its sessions (lesson 6). |
| Existing WSL/Docker workflows break | All Phase 1 changes are gated on `database.engine` or are Windows-only files |
