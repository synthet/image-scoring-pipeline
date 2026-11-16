"""Native OpenVINO probe (#875): devices, compile on a device, parity against an ORT CPU reference, latency.

Usage:
    python ov_probe.py <model.onnx> <CPU|GPU|GPU.1|NPU> <ref.npz> [--precision f16|f32]

``--precision`` sets ``INFERENCE_PRECISION_HINT``. The Intel GPU plugin defaults to f16; f32 restores
CPU-level parity at roughly 1.5x the latency. ``ref.npz`` comes from ``ort_probe.py --write-ref``.
"""

import json
import statistics
import sys
import time

import numpy as np
import openvino as ov
import openvino.properties.hint as hint


def main() -> None:
    model_path, device, ref_path = sys.argv[1:4]
    config = {}
    if "--precision" in sys.argv:
        config[hint.inference_precision()] = sys.argv[sys.argv.index("--precision") + 1]

    core = ov.Core()
    info = {
        "ov_version": ov.__version__,
        "devices": {d: core.get_property(d, "FULL_DEVICE_NAME") for d in core.available_devices},
        "config": config,
    }
    model = core.read_model(model_path)
    inp = model.inputs[0]
    partial = inp.get_partial_shape()
    shape = [d.get_length() if d.is_static else 1 for d in partial]
    if partial.is_dynamic:
        model.reshape({inp.get_any_name(): shape})

    start = time.perf_counter()
    compiled = core.compile_model(model, device, config)
    info["compile_s"] = round(time.perf_counter() - start, 2)
    info["precision"] = str(compiled.get_property(hint.inference_precision()))

    rng = np.random.default_rng(0)
    if inp.get_element_type() == ov.Type.i64:
        x = np.zeros(shape, dtype=np.int64)
        x[..., 0] = 49406
        x[..., 1:11] = rng.integers(1, 49405, size=x[..., 1:11].shape)
        x[..., 11] = 49407
    else:
        x = rng.standard_normal(shape).astype(np.float32)

    request = compiled.create_infer_request()
    result = request.infer({0: x})
    outs = [np.asarray(result[o]) for o in compiled.outputs]
    for _ in range(3):
        request.infer({0: x})
    times = []
    for _ in range(20):
        t = time.perf_counter()
        request.infer({0: x})
        times.append((time.perf_counter() - t) * 1000)
    info["warm_ms_p50"] = round(statistics.median(times), 2)

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
