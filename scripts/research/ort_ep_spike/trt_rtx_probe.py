"""TensorRT-RTX via Windows ML (#875 follow-up).

A worker process does the pywinrt part (bootstrap, catalog, ensure_ready) and prints the EP library
path; the main process never imports pywinrt, registers the library with ONNX Runtime, and measures
session creation, the first run (JIT engine build), warm latency and parity against a CPU reference.

Usage: python trt_rtx_probe.py <model.onnx> <cpu_ref.npz> [--opt key=value ...]
"""
import json
import statistics
import subprocess
import sys
import time

import numpy as np

EP = "NvTensorRTRTXExecutionProvider"


def worker() -> None:
    import winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap as bootstrap

    with bootstrap.initialize():
        import winui3.microsoft.windows.ai.machinelearning as winml

        catalog = winml.ExecutionProviderCatalog.get_default()
        provider = next(p for p in catalog.find_all_providers() if p.name == EP)
        before = int(provider.ready_state)
        result = provider.ensure_ready_async().get()
        print(json.dumps({"name": provider.name, "library_path": provider.library_path,
                          "ready_state_before": before, "ensure_status": int(result.status)}))


def make_input(type_name, shape):
    rng = np.random.default_rng(0)
    if "int64" in type_name:
        t = np.zeros(shape, dtype=np.int64)
        t[..., 0] = 49406
        t[..., 1:11] = rng.integers(1, 49405, size=t[..., 1:11].shape)
        t[..., 11] = 49407
        return t
    return rng.standard_normal(shape).astype(np.float32)


def main() -> None:
    model, ref_path = sys.argv[1], sys.argv[2]
    opts = {}
    for i, a in enumerate(sys.argv):
        if a == "--opt":
            k, v = sys.argv[i + 1].split("=", 1)
            opts[k] = v
    out = subprocess.check_output([sys.executable, __file__, "--worker"], text=True, stderr=subprocess.DEVNULL)
    ep = json.loads(out.strip().splitlines()[-1])

    import onnxruntime as ort

    info = {"ort": ort.__version__, "opts": opts, "ready_state_before": ep["ready_state_before"],
            "ensure_status": ep["ensure_status"], "library": ep["library_path"].split("\\")[-1]}
    ort.register_execution_provider_library(ep["name"], ep["library_path"])
    devs = [d for d in ort.get_ep_devices() if d.ep_name == EP]
    info["ep_devices"] = [f"{d.ep_name}:{d.device.type}:{d.device.vendor}" for d in devs]
    so = ort.SessionOptions()
    so.add_provider_for_devices([devs[0]], opts)
    t = time.perf_counter()
    sess = ort.InferenceSession(model, sess_options=so)
    info["session_create_s"] = round(time.perf_counter() - t, 2)
    info["session_providers"] = sess.get_providers()
    inp = sess.get_inputs()[0]
    shape = [d if isinstance(d, int) else (1 if i == 0 else 640) for i, d in enumerate(inp.shape)]
    feed = {inp.name: make_input(inp.type, shape)}
    t = time.perf_counter()
    outs = [np.asarray(o) for o in sess.run(None, feed)]
    info["first_run_s"] = round(time.perf_counter() - t, 2)
    for _ in range(3):
        sess.run(None, feed)
    times = []
    for _ in range(20):
        t = time.perf_counter()
        sess.run(None, feed)
        times.append((time.perf_counter() - t) * 1000)
    info["warm_ms_p50"] = round(statistics.median(times), 2)
    ref = np.load(ref_path)
    info["max_abs_diff_vs_cpu"] = [
        float(np.max(np.abs(o.astype(np.float64) - ref[f"arr_{i}"]))) if o.shape == ref[f"arr_{i}"].shape
        else f"shape {o.shape} vs {ref[f'arr_{i}'].shape}" for i, o in enumerate(outs)]
    info["max_abs_ref"] = [float(np.max(np.abs(ref[f"arr_{i}"]))) for i in range(len(outs))]
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    worker() if "--worker" in sys.argv else main()
