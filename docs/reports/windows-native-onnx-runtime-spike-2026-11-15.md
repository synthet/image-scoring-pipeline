---
type: Report
title: Windows-native ONNX Runtime GPU and NPU spike
description: Which ONNX Runtime execution providers run natively on Windows on the 8 GB laptop, with latency, parity, NPU feasibility, Windows ML from Python and the gotchas found.
resource: reports/windows-native-onnx-runtime-spike-2026-11-15.md
tags: [onnx, windows, inference, gpu, npu, directml, openvino, windows-ml, benchmark, report]
timestamp: 2026-11-16T01:30:00Z
okf_version: 0.2
---

# Windows-native ONNX Runtime GPU and NPU spike

ONNX models run natively on Windows on the RTX 4060 laptop through four routes; NPU inference is not possible on this machine because its CPU has no NPU. Issue: [#875](https://github.com/synthet/image-scoring-pipeline/issues/875).

Related: [WINDOWS_NATIVE_WEBUI_PLAN.md](../planning/setup/WINDOWS_NATIVE_WEBUI_PLAN.md), [ONNX_CONVERSION_FEASIBILITY.md](../planning/models/ONNX_CONVERSION_FEASIBILITY.md), [timing-baseline-2026-10-18](timing-baseline-2026-10-18.md).

## TL;DR

- **GPU, natively, today:** DirectML, CUDA, the OpenVINO execution provider and Windows ML from Python all ran here. Nothing needed WSL or Docker.
- **NPU:** none on this machine. OpenVINO lists only `CPU`, `GPU.0` (Intel UHD) and `GPU.1` (RTX 4060), and neither ORT nor the Windows ML catalog lists an NPU device. On other hardware the Windows ML catalog serves OpenVINO (Intel Core Ultra), QNN (Snapdragon X) and VitisAI (Ryzen AI) on Windows 11 24H2 or later. That path is **untested** here, and per-model NPU constraints (static shapes, quantization, operator coverage) were not checked.
- **Parity:** DirectML matches the CPU EP to about 1e-6. CUDA needs `use_tf32=0` for CPU-level parity. The Intel iGPU needs an f32 precision hint.
- **Planning-doc correction:** Windows ML has a documented Python route (`onnxruntime-windowsml` plus the `wasdk-*` packages), and it ran inference in-process. The earlier "needs a non-Python integration boundary" claim is superseded. It is still a separate ORT distribution and depends on the Windows App SDK runtime.
- **DirectML session lifetime:** for some graphs, freeing a newer session while an older session of the same graph is alive segfaults the process. A global lock does not prevent it. Keep DirectML sessions for the process lifetime.

## Setup

| Item | Value |
|---|---|
| Machine | i7-13620H (Raptor Lake-H, no NPU), RTX 4060 Laptop 8 GB (driver 621.14 / WDDM 32.0.16.2114), Intel UHD iGPU |
| OS | Windows 11 build 26300; Windows App SDK runtime 2.3–2.6 already installed |
| Python | uv-managed CPython 3.12.13, one venv per ORT distribution (never co-installed) |
| Probes | [`scripts/research/ort_ep_spike/`](../../scripts/research/ort_ep_spike/); exact package sets in `envs/*.txt` |
| Inputs | Seeded random tensors, so latency and numerics only. Real-photo parity is in [its own section](#real-photo-parity-application-scoring-loop). |

| Route | Package(s) | ORT | Selected EP |
|---|---|---|---|
| CPU reference | `onnxruntime` | 1.32.0 | CPU |
| DirectML | `onnxruntime-directml` | 1.24.4 | `DmlExecutionProvider` (binds to the RTX 4060) |
| CUDA | `onnxruntime-gpu[cuda,cudnn]` (pip CUDA 13.x, cuDNN 9.28) | 1.32.0 | `CUDAExecutionProvider` |
| OpenVINO EP | `onnxruntime-openvino` + `openvino==2025.4.1` | 1.24.1 | `OpenVINOExecutionProvider` |
| OpenVINO native | `openvino` 2026.4.1 | — | OpenVINO runtime |
| Windows ML | `onnxruntime-windowsml` + `wasdk-Microsoft.Windows.AI.MachineLearning[all]==2.3.0` + `wasdk-…DynamicDependency.Bootstrap==2.3.0` | 1.25.2 | included `DmlExecutionProvider` |

The test graphs were the pipeline's `models/rtmdet_tiny_coco.onnx`, plus a sibling project's ONNX exports of RTMDet-tiny COCO with embedded NMS (640), RTMPose-m AP-10K (256), an RTMPose-tiny three-keypoint head (256), U²-Net-p (320), and OpenCLIP ViT-B/32 image and text towers (dynamic batch, plus a static batch-1 image export).

## Latency (warm p50, ms, batch 1)

| Graph | ORT CPU | DirectML | CUDA | OV native CPU | OV EP CPU | iGPU OV native / EP |
|---|---|---|---|---|---|---|
| RTMDet-tiny, embedded NMS | 92.3 | 42.0 | 40.5 | 37.6 | 55.7 | 81.9 / fails |
| RTMPose-m | 9.6 | 5.3 | 3.3 | 15.0 | 16.1 | 6.4 / 26.5 |
| U²-Net-p | 100.9 | 8.4 | 16.1 | 79.6 | 108.9 | 49.3 / 49.5 |
| RTMPose-tiny (3 kpt) | 0.9 | 2.8 | 1.9 | 1.4 | 2.4 | 1.7 / 6.7 |
| ViT-B/32 image (dynamic) | 23.5 | 8.2 | 3.9 | 44.0 | 44.3 | 40.9 / 39.6 |
| ViT-B/32 text | 18.6 | 8.7 | 5.1 | 17.3 | 16.1 | 15.9 / 16.5 |
| ViT-B/32 image (static batch 1) | 23.5 | **fails** `E_INVALIDARG` | 4.0 | 24.9 | — | 24.8 |
| Pipeline `rtmdet_tiny_coco.onnx` (no NMS) | 30.2 | 6.3 | — | — | — | — |

Random input inflates the NMS graph's timings, because noise produces many candidate boxes. Session creation is 0.1–1 s on CPU and CUDA. On DirectML it is 0.4–1 s per graph, and the first U²-Net-p compile took 5.8 s. OpenVINO iGPU compiles take 3–16 s.

## Parity against the ORT CPU EP

| Route | Max abs diff | Cause, and how to remove it |
|---|---|---|
| DirectML | ~1e-6 (NMS graph 3.4e-4) | — |
| CUDA, defaults | 1e-3 to 2e-2; NMS graph box outputs differ by up to 7e+02 | TF32 is on by default (`use_tf32=1`). With `use_tf32=0`: NMS graph 3.7e-4, RTMPose-m 1.1e-6, U²-Net-p 2.7e-5, at 38 / 4.6 / 13.1 ms. |
| OpenVINO CPU (EP or native) | ~1e-6 | — |
| OpenVINO iGPU | 1e-2 to 1e-1 | The GPU default `INFERENCE_PRECISION_HINT` is `float16`. With `f32`: U²-Net-p 3.3e-5, RTMPose-m 7e-7, ViT-B/32 2.5e-6, at about 1.5× the latency. |

For the ONNX conversion plan's parity gate: record `use_tf32` (or pin it to `0`) and the OpenVINO precision hint in every parity run, next to the EP list.

## Real-photo parity (application scoring loop)

Forty fixed library thumbnails (512 px, sorted sample) went through a sibling application's detector → pose → mask loop and its six criterion scores, once per route.

| Route | ms / photo (incl. decode, EXIF) | Subjects found (CPU: 25/40) | Box IoU min | Criteria changed | Max composite Δ | Rank τ |
|---|---|---|---|---|---|---|
| ORT CPU | 579 | — | — | — | — | — |
| DirectML | 106 | identical | 1.000 | 0/40 | 0 | 1.000 |
| CUDA, TF32 on (default) | 111 | identical | 0.996 | 6/40 | 0.5 | 0.997 |
| CUDA, `use_tf32=0` | 104 | identical | 1.000 | 0/40 | 0 | 1.000 |
| OpenVINO EP CPU | 199 | identical | 1.000 | 0/40 | 0 | 1.000 |

## DirectML session-lifetime crash

Repro: [`dml_free_order.py`](../../scripts/research/ort_ep_spike/dml_free_order.py), plain ORT, single thread.

| Graph | `newer-freed`: A alive, B created, run, freed, then A runs | `older-freed` (replace pattern) |
|---|---|---|
| RTMDet-tiny with embedded NMS | **segfault** on the first iteration (DirectML 1.24.4 and Windows ML 1.25.2) | OK |
| RTMPose-m | **segfault** (3/3 reruns, both ORT builds) | OK |
| U²-Net-p | OK | OK |
| Pipeline RTMDet (no NMS) | OK | OK |

- The crash fires when the surviving older session next runs, not at the free.
- Only same-graph pairs were tested.
- CUDA, CPU and the OpenVINO EP (CPU device, with `add_openvino_libs_to_path()`, so `get_providers()[0]` is `OpenVINOExecutionProvider`) pass the same sequence on both affected graphs, in both orders.
- In a threaded variant (a long-lived session plus workers creating and freeing sessions), the crash also happened with one lock around every create, run and free.
- This adds to the parity lesson in [ONNX_CONVERSION_FEASIBILITY.md](../planning/models/ONNX_CONVERSION_FEASIBILITY.md) that concurrent DirectML sessions crash. Serializing calls is not enough: keep one session per graph for the process lifetime, and never free a session while an older session of the same graph is alive.

## Windows ML from Python

- **Works with a uv or python.org interpreter.** `bootstrap.initialize()` then `ExecutionProviderCatalog.get_default().find_all_providers()` listed:
  - `OpenVINOExecutionProvider` (certified);
  - `NvTensorRTRTXExecutionProvider` (certified, RTX 30xx and newer);
  - `WebGpuExecutionProvider` (uncertified).

  All three are `NOT_PRESENT`, which means they download on demand. QNN and VitisAI are absent, matching the hardware. Inference on the included DirectML EP ran at 5.9 ms with a diff of 1.3e-6 against CPU (RTMPose-m).
- **Fails with the Microsoft Store Python.** The same bootstrap fails with `0x80070032` ("request not supported"), as Microsoft's docs say.
- **Version pairing:** `wasdk-*==2.3.0` resolved `onnxruntime-windowsml` 1.25.2 and matches the installed App SDK runtime 2.3.
- **Registration:** Microsoft's Python sample says not to use the bulk register call, because "it won't register EPs to the python ort env". Register each provider with `ensure_ready_async()` and `ort.register_execution_provider_library()`.
- **Not run:** `ensure_ready_async()` for TensorRT-RTX installs a system package, so it waits for owner approval. TensorRT-RTX latency is therefore unknown.

## Gotchas

1. **OpenVINO EP version pairing.** `onnxruntime-openvino` 1.24.1 next to the latest `openvino` (2026.4.1) creates the session without error but silently runs on the CPU EP (`Error 127` loading `onnxruntime_providers_openvino.dll`). `openvino==2025.4.1`, the version the wheel was built against, works. Always check `session.get_providers()[0]`.
2. **The OpenVINO EP on Windows** needs `onnxruntime.tools.add_openvino_win_libs.add_openvino_libs_to_path()` before the session is created.
3. **DirectML lags:** `onnxruntime-directml` is at 1.24.4 while ORT is at 1.32.0, and Windows ML lists DirectML as "legacy".
4. **Classic TensorRT EP** was not tested. ORT's compatibility table stops at 1.22 (TensorRT 10.9, CUDA 12), while the 1.32 PyPI GPU build targets CUDA 13. For NVIDIA on Windows, the TensorRT-RTX EP through Windows ML is the documented route.
5. **CUDA 13 wheels:** they worked with the installed driver (621.14). The CUDA venv takes 1.9 GB.

## Implications for the plans

- The pipeline's RTMDet fallback already accepts `providers`. On this laptop it gets about 5× from DirectML (30 → 6 ms), but the [blockers doc](../specs/pipeline-streamlining/07-blockers-and-decisions.md) keeps it on CPU on purpose, to save VRAM.
- Option D of the [native plan](../planning/setup/WINDOWS_NATIVE_WEBUI_PLAN.md) gains a third Python-reachable GPU route (Windows ML). Its NVIDIA EP (TensorRT-RTX) is still unbenchmarked.
- NPU inference stays out of scope until there is NPU hardware to test on.
- **Open:** per-model NPU constraints (static shapes, quantization, operator coverage) were not checked. Input shapes for a future check:
  - static: the NMS RTMDet (`1×3×640×640`, but a variable box count `N` in its outputs), U²-Net-p (`1×3×320×320`), and the static ViT-B/32 export;
  - dynamic batch: both RTMPose graphs and the dynamic ViT-B/32 image and text towers.

## Reproduce

All commands run from `scripts/research/ort_ep_spike/`, with one uv venv per row of `envs/*.txt` (`uv venv --python 3.12 <env>`, then `uv pip install -r envs/<env>.txt`).

```powershell
# CPU reference, then the same graph on each provider
cpu\Scripts\python ort_probe.py <model.onnx> CPUExecutionProvider ref.npz --write-ref
dml\Scripts\python  ort_probe.py <model.onnx> DmlExecutionProvider ref.npz
cuda\Scripts\python ort_probe.py <model.onnx> CUDAExecutionProvider ref.npz --opt use_tf32=0
ov\Scripts\python   ort_probe.py <model.onnx> OpenVINOExecutionProvider ref.npz --opt device_type=CPU
ovnative\Scripts\python ov_probe.py <model.onnx> GPU ref.npz --precision f32

# Windows ML (uv or python.org CPython, not the Store Python)
winml\Scripts\python winml_list.py
winml\Scripts\python winml_wrap.py ort_probe.py <model.onnx> DmlExecutionProvider ref.npz

# DirectML session-lifetime crash: on affected graphs the process dies with an access violation
# ($LASTEXITCODE -1073741819 / 0xC0000005 in PowerShell; 139 in Git Bash)
dml\Scripts\python dml_free_order.py <model.onnx> DmlExecutionProvider newer-freed
```

The latency table's seven non-pipeline graphs and the real-photo scoring loop come from a sibling project. That loop's scripts live outside this repository and are not needed for the provider findings above.

## Sources (checked 2026-11-15)

- [Windows ML execution providers](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/supported-execution-providers), [install and deploy](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/distributing-your-app), [register execution providers](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/register-execution-providers)
- [Intel Windows ML support](https://www.intel.com/content/www/us/en/developer/articles/guide/windows-ml-support.html) (NPU: Core Ultra Series 1 or newer; iGPU: 12th Gen or newer)
- [ORT CUDA EP](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html) (`use_tf32`), [DirectML EP](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html), [OpenVINO EP](https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html), [TensorRT EP](https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html)
