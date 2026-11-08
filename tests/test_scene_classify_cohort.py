"""classify_cohort.py: the scene-only labeller, run locally or on the GPU runner (#809)."""

import json
import sys
from types import SimpleNamespace

import pytest

from modules.remote_gpu.client import FallbackGpuClient, RemoteGpuUnavailable
from modules.remote_gpu.proxies import RemoteSceneClassifier
from modules.scene_route import SceneClassifier, SceneResult
from scripts.research.scene_route import classify_cohort


class FakeRunner:
    def __init__(self, base_url, fail=False):
        self.base_url = base_url
        self.fail = fail
        self.checked = []

    def check_phase(self, phase):
        self.checked.append(phase)
        if self.fail:
            raise RemoteGpuUnavailable("runner down")
        return {}


def _fallback_route(monkeypatch, runner_fails=False):
    runner = FakeRunner("http://tridentx:7870", fail=runner_fails)
    embedded = FakeRunner("embedded")
    monkeypatch.setattr("modules.remote_gpu.client.get_client",
                        lambda: FallbackGpuClient([runner, embedded]))
    return runner, embedded


def test_local_builds_and_loads_the_local_classifier(monkeypatch):
    loaded = []
    monkeypatch.setattr(SceneClassifier, "load", lambda self: loaded.append(self.backend))

    clf = classify_cohort.make_classifier("siglip2_base", "scene_v2", remote=False)

    assert type(clf) is SceneClassifier
    assert loaded == ["siglip2_base"]


def test_remote_uses_the_configured_runner_and_never_the_fallback(monkeypatch):
    runner, embedded = _fallback_route(monkeypatch)

    clf = classify_cohort.make_classifier("siglip2_base", "scene_v2", remote=True)

    assert isinstance(clf, RemoteSceneClassifier)
    assert clf._client is runner
    assert runner.checked == ["localization"]
    assert embedded.checked == []


def test_remote_fails_loudly_when_the_runner_is_not_ready(monkeypatch):
    runner, embedded = _fallback_route(monkeypatch, runner_fails=True)

    with pytest.raises(RemoteGpuUnavailable):
        classify_cohort.make_classifier("siglip2_base", "scene_v2", remote=True)
    assert embedded.checked == []


def test_classify_passes_remote_through_and_records_each_image(monkeypatch, tmp_path):
    seen = {}

    class FakeClassifier:
        def load(self):
            pass

        def classify(self, image):
            return SceneResult(probs={"wildlife_bird": 0.9}, cosines={}, top_label="wildlife_bird",
                               top_prob=0.9, version="scene_v2/siglip2_base/test")

    def fake_make(backend, prompt_set, remote):
        seen["args"] = (backend, prompt_set, remote)
        return FakeClassifier()

    saved = []
    decoded = SimpleNamespace(image=object(), descriptor=SimpleNamespace(rendition_hash="r1"))
    monkeypatch.setattr(classify_cohort, "make_classifier", fake_make)
    monkeypatch.setattr("modules.localization.decode_for_localization", lambda path: decoded)
    monkeypatch.setattr("modules.scene_route.save_scene_label",
                        lambda iid, result, **kw: saved.append((iid, result.top_label, kw)))
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"images": [{"image_id": 7, "file_path": "a.nef"}]}), encoding="utf-8")
    out = tmp_path / "out.jsonl"

    counts = classify_cohort.classify(snapshot, out, "siglip2_base", 0, "scene_v2", remote=True)

    assert seen["args"] == ("siglip2_base", "scene_v2", True)
    assert counts["ok"] == 1
    assert saved == [(7, "wildlife_bird", {"backend": "siglip2_base", "rendition_hash": "r1"})]
    assert json.loads(out.read_text(encoding="utf-8"))["top_label"] == "wildlife_bird"


@pytest.mark.parametrize("argv, remote", [([], False), (["--remote"], True)])
def test_cli_remote_flag(monkeypatch, tmp_path, argv, remote):
    calls = []
    monkeypatch.setattr(classify_cohort, "classify", lambda *a, **kw: calls.append((a, kw)) or {})
    monkeypatch.setattr(sys, "argv", ["classify_cohort.py", "--snapshot", str(tmp_path / "s.json"),
                                      "--out", str(tmp_path / "o.jsonl"), *argv])

    classify_cohort.main()

    assert calls[0][1] == {"remote": remote}
