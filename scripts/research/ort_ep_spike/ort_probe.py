"""ONNX Runtime execution-provider probe (#875).

Reports the available providers, the provider that actually runs the session, warm latency, and the
max abs difference against a CPU reference written by an earlier ``--write-ref`` run.

Usage:
    python ort_probe.py <model.onnx> CPUExecutionProvider ref.npz --write-ref
    python ort_probe.py <model.onnx> <provider> ref.npz [--opt key=value ...]

Examples of provider options: ``--opt use_tf32=0`` (CUDA), ``--opt device_type=GPU`` (OpenVINO).
Inputs are seeded random tensors (CLIP-style tokens for int64 inputs), so results cover latency and
numerics only.
"""

import json
import statistics
import sys
import time

import numpy as np
import onnxruntime as ort


def parse_opts(argv: list[str]) -> dict[str, str]:
    opts = {}
    for i, arg in enumerate(argv):
        if arg == "--opt":
            key, value = argv[i + 1].split("=", 1)
            opts[key] = value
    return opts


def make_input(type_name: str, shape: list[int]) -> np.ndarray:
    rng = np.random.default_rng(0)
    if "int64" in type_name:
        tokens = np.zeros(shape, dtype=np.int64)
        tokens[..., 0] = 49406  # start of text
        tokens[..., 1:11] = rng.integers(1, 49405, size=tokens[..., 1:11].shape)
        tokens[..., 11] = 49407  # end of text
        return tokens
    return rng.standard_normal(shape).astype(np.float32)


def main() -> None:
    model, want, ref_path = sys.argv[1], sys.argv[2], sys.argv[3]
    write_ref = "--write-ref" in sys.argv
    opts = parse_opts(sys.argv)

    if want == "CUDAExecutionProvider" and hasattr(ort, "preload_dlls"):
        ort.preload_dlls()
    if want == "OpenVINOExecutionProvider":
        import onnxruntime.tools.add_openvino_win_libs as ov_libs

        ov_libs.add_openvino_libs_to_path()

    info = {"ort_version": ort.__version__, "available": ort.get_available_providers(), "opts": opts}
    if hasattr(ort, "get_ep_devices"):
        devices = []
        for dev in ort.get_ep_devices():
            hw = getattr(dev, "device", None) or getattr(dev, "hardware_device", None)
            devices.append(f"{dev.ep_name}:{getattr(hw, 'type', '?')}")
        info["ep_devices"] = devices

    if want == "CPUExecutionProvider":
        providers = [want]
    else:
        providers = [(want, opts), "CPUExecutionProvider"]
    start = time.perf_counter()
    sess = ort.InferenceSession(model, sess_options=ort.SessionOptions(), providers=providers)
    info["session_create_s"] = round(time.perf_counter() - start, 2)
    info["session_providers"] = sess.get_providers()  # [0] is the provider that runs it

    inp = sess.get_inputs()[0]
    shape = [d if isinstance(d, int) else (1 if i == 0 else 640) for i, d in enumerate(inp.shape)]
    feed = {inp.name: make_input(inp.type, shape)}

    outs = [np.asarray(o) for o in sess.run(None, feed)]
    for _ in range(3):
        sess.run(None, feed)
    times = []
    for _ in range(20):
        t = time.perf_counter()
        sess.run(None, feed)
        times.append((time.perf_counter() - t) * 1000)
    info["warm_ms_p50"] = round(statistics.median(times), 2)
    info["warm_ms_min"] = round(min(times), 2)

    if write_ref:
        np.savez(ref_path, *outs)
    else:
        ref = np.load(ref_path)
        diffs = []
        for i, out in enumerate(outs):
            expected = ref[f"arr_{i}"]
            if out.shape == expected.shape:
                diffs.append(float(np.max(np.abs(out.astype(np.float64) - expected))))
            else:
                diffs.append(f"shape {out.shape} vs {expected.shape}")
        info["max_abs_diff_vs_cpu"] = diffs
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
