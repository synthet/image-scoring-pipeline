"""DirectML session-lifetime repro (#875), plain ONNX Runtime, single thread.

Session A (older) stays alive while session B (newer) of the same graph is created, run and freed;
then A runs again (``newer-freed``). ``older-freed`` is the replace pattern: A is freed and B is kept.

Usage: python dml_free_order.py <model.onnx> <provider> <newer-freed|older-freed>

On DirectML some graphs die with an access violation in ``newer-freed`` when A next runs
(PowerShell ``$LASTEXITCODE`` -1073741819 / 0xC0000005; Git Bash 139). CPU, CUDA and the OpenVINO EP pass.
"""

import gc
import sys

import numpy as np
import onnxruntime as ort


def make_session(model: str, provider: str) -> ort.InferenceSession:
    return ort.InferenceSession(model, providers=[provider, "CPUExecutionProvider"])


def main() -> None:
    model, provider, order = sys.argv[1:4]
    if provider == "CUDAExecutionProvider":
        ort.preload_dlls()
    if provider == "OpenVINOExecutionProvider":
        import onnxruntime.tools.add_openvino_win_libs as ov_libs

        ov_libs.add_openvino_libs_to_path()
    a = make_session(model, provider)
    inp = a.get_inputs()[0]
    shape = [d if isinstance(d, int) else 1 for d in inp.shape]
    feed = {inp.name: np.random.default_rng(0).standard_normal(shape).astype(np.float32)}
    a.run(None, feed)
    print("A ran on", a.get_providers()[0], flush=True)
    for k in range(5):
        b = make_session(model, provider)
        b.run(None, feed)
        if order == "newer-freed":
            del b
            gc.collect()
            a.run(None, feed)
        else:
            del a
            gc.collect()
            b.run(None, feed)
            a = b
        print("iteration", k, "ok", flush=True)
    print("OK")


if __name__ == "__main__":
    main()
