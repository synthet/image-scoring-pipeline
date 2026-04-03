# Gradio Decision for `image-scoring`

## Short answer

No, Gradio is not the best general-purpose production inference server for CUDA, PyTorch, or TensorFlow workloads.

For this repository, that does not make Gradio the wrong choice. `image-scoring` is primarily an interactive image-scoring and review application with a built-in API, not a dedicated high-throughput inference service. In that shape, Gradio remains a reasonable UI layer.

## What Gradio Does vs. What Runs on GPU

Gradio is the application and UI layer. It renders the web interface, wires user interactions to Python functions, and hosts an operator-friendly workflow.

It is not the thing that makes CUDA work. GPU execution comes from the model runtimes and libraries underneath it:

- `TensorFlow` backs MUSIQ-related scoring components in this project.
- `PyTorch` backs LIQE and the CLIP/BLIP-style model workloads used for tagging and captioning where applicable.
- `CUDA` is the acceleration layer used by those runtimes when the environment and models support it.
- `FastAPI` is the API and control plane already present in this repo, separate from the model runtime itself.

That distinction matters because replacing Gradio does not automatically improve raw GPU performance. If the bottleneck is model loading, batching, concurrency, memory pressure, or scheduling, those issues need to be solved in the runtime and serving layer, not by swapping the UI framework.

## Current Architecture in `image-scoring`

This repository already uses a hybrid structure that is close to the right shape for an interactive ML tool:

- [`webui.py`](../webui.py) creates the root `FastAPI` application.
- [`modules/api.py`](../modules/api.py) exposes REST endpoints under `/api`.
- Gradio is mounted into the FastAPI app rather than replacing it.
- Model execution happens in the scoring and tagging pipeline, not inside Gradio itself.

In practice, the current stack is:

| Component | Role | Why it fits this repo |
|-----------|------|------------------------|
| **Gradio** | UI/application layer | Good for internal, operator-driven workflows and fast iteration |
| **FastAPI** | API/control plane | Useful for REST endpoints, status, automation, and integration |
| **TensorFlow / PyTorch + CUDA** | Model runtime | Actually runs the scoring, tagging, and captioning workloads |
| **Database + pipeline workers** | Long-running orchestration | Handles batch processing outside the UI request cycle |

That is already much closer to a sensible production architecture than "Gradio only." The project is not relying on Gradio as its sole backend abstraction.

## When Another Framework Would Be Better

Gradio stops being the best fit when the project's center of gravity shifts away from an interactive tool and toward a serving platform.

You should consider another primary serving layer if one or more of these become important:

- multiple external clients need a stable service interface
- deployment becomes strictly API-first rather than UI-first
- request concurrency and throughput become more important than operator interaction
- model-serving isolation becomes necessary for reliability or deployment independence
- GPU scheduling, batching, and utilization become first-order concerns

If that happens, the alternatives are not interchangeable:

- **FastAPI** is the right next step for a custom API-first service when you want full control over routes, auth, jobs, streaming, and service boundaries.
- **BentoML** is the better fit when you want a Python-first model-serving framework with packaging and deployment conventions built around inference workloads.
- **NVIDIA Triton** is the stronger choice when GPU throughput, batching, concurrency, and multi-model serving become the primary problem.

Secondary options are more niche here:

- **TorchServe** is relevant only if the serving stack becomes heavily PyTorch-specific.
- **TensorFlow Serving** is relevant only if the stack becomes strongly TensorFlow-specific.
- **vLLM / TGI** are LLM-serving tools and are not central to the current vision-model architecture in this repo.

## Recommended Paths

### 1. Keep current Gradio + FastAPI

This is the right default for `image-scoring` today.

Keep Gradio as the human-facing UI and keep FastAPI as the API/control plane. Improve the pipeline, model lifecycle, and worker behavior if performance issues appear. Do not replace Gradio just to "run CUDA better," because that is not where raw inference performance comes from.

### 2. Gradio + separate FastAPI service

Use this when backend responsibilities expand beyond what should live inside the current WebUI process.

This is the right move if Electron, automation, or external clients start depending more heavily on the API, or if you want clearer separation between interactive UI concerns and backend job execution.

### 3. Gradio or separate frontend + Triton/BentoML

Use this only when production inference scaling becomes a real requirement.

If the project needs higher request concurrency, model isolation, explicit deployment packaging, or GPU-aware serving features such as batching and multi-model scheduling, move inference behind BentoML or Triton and treat Gradio as optional on top.

## Bottom line

`image-scoring` should keep Gradio as its UI layer unless the product changes shape. The current architecture already separates UI, API, and model execution reasonably well: Gradio handles interaction, FastAPI handles service endpoints, and TensorFlow/PyTorch handle actual CUDA-backed inference. Replace or split the serving layer only when operational requirements such as API-first deployment, external clients, higher concurrency, or GPU scheduling justify the added complexity.

## Sources

- [Gradio docs](https://www.gradio.app/)
- [FastAPI deployment docs](https://fastapi.tiangolo.com/deployment/)
- [BentoML GPU inference docs](https://docs.bentoml.com/en/latest/build-with-bentoml/gpu-inference.html)
- [NVIDIA Triton docs](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/index.html)
