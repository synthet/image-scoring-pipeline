"""GPU_RUNNER_TF_DEVICE=cpu: TensorFlow models run on CPU on a runner whose GPU TF can't use (#887)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from modules.remote_gpu.server import configure_tensorflow_devices


def fake_tf(physical, visible):
    calls = []
    config = SimpleNamespace(
        experimental=SimpleNamespace(
            list_physical_devices=lambda kind=None: list(physical),
            set_memory_growth=lambda device, enabled: calls.append(("growth", device)),
        ),
        get_visible_devices=lambda kind=None: list(visible),
        set_visible_devices=lambda devices, kind=None: calls.append(("visible", list(devices), kind)),
    )
    return SimpleNamespace(config=config), calls


def test_cpu_setting_hides_gpu_from_tensorflow(monkeypatch):
    tf, calls = fake_tf(["GPU:0"], ["GPU:0"])
    monkeypatch.setitem(sys.modules, "tensorflow", tf)
    monkeypatch.setenv("GPU_RUNNER_TF_DEVICE", "CPU")
    assert configure_tensorflow_devices() is True
    assert calls == [("visible", [], "GPU")]


@pytest.mark.parametrize("value", [None, "", "gpu", "auto"])
def test_default_leaves_tensorflow_alone(monkeypatch, value):
    # A None module makes any import fail, so this also proves TensorFlow is not imported.
    monkeypatch.setitem(sys.modules, "tensorflow", None)
    if value is None:
        monkeypatch.delenv("GPU_RUNNER_TF_DEVICE", raising=False)
    else:
        monkeypatch.setenv("GPU_RUNNER_TF_DEVICE", value)
    assert configure_tensorflow_devices() is False


def test_unknown_value_stops_the_runner(monkeypatch):
    monkeypatch.setenv("GPU_RUNNER_TF_DEVICE", "cuda")
    with pytest.raises(SystemExit, match="GPU_RUNNER_TF_DEVICE"):
        configure_tensorflow_devices()


def _musiq_setup(monkeypatch, physical, visible):
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    tf, calls = fake_tf(physical, visible)
    monkeypatch.setitem(sys.modules, "tensorflow", tf)
    scorer = MultiModelMUSIQ.__new__(MultiModelMUSIQ)
    scorer._setup_gpu()
    return scorer, calls


def test_musiq_uses_cpu_when_tensorflow_sees_no_gpu(monkeypatch):
    scorer, calls = _musiq_setup(monkeypatch, physical=["GPU:0"], visible=[])
    assert (scorer.device, scorer.gpu_available) == ("/CPU:0", False)
    assert calls == []  # memory growth on a hidden GPU would initialize it


def test_musiq_keeps_gpu_when_visible(monkeypatch):
    scorer, calls = _musiq_setup(monkeypatch, physical=["GPU:0"], visible=["GPU:0"])
    assert (scorer.device, scorer.gpu_available) == ("/GPU:0", True)
    assert calls == [("growth", "GPU:0")]
