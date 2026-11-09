"""Scene route in the localization runner (spec 05 AC-7, AC-8; #412). No model or database."""

from types import SimpleNamespace

import pytest

import modules.localization as loc
import modules.localization_runner as lr
import modules.scene_route as sr
from modules.scene_route import SceneResult


class _Classifier:
    def __init__(self, bird=0.0, error=None):
        self.bird, self.error = bird, error

    def classify(self, image):
        if self.error:
            raise self.error
        return SceneResult(probs={"wildlife_bird": self.bird, "landscape": 1 - self.bird}, cosines={},
                           top_label="wildlife_bird" if self.bird >= 0.5 else "landscape",
                           top_prob=max(self.bird, 1 - self.bird), version="scene_v2/test/abc")


@pytest.fixture
def calls(monkeypatch, tmp_path):
    log = {"decode": 0, "detect": [], "skip": [], "saved": []}
    decoded = SimpleNamespace(image=object(), descriptor=SimpleNamespace(rendition_hash="r1"))

    def decode(path):
        log["decode"] += 1
        if path.endswith("broken.jpg"):
            raise loc.DecodeError("decode_error: bad")
        return decoded

    monkeypatch.setattr(loc, "decode_for_localization", decode)
    monkeypatch.setattr(lr, "localize_image",
                        lambda iid, fp, ctx, max_regions, job_id, decoded=None, reuse_unchanged=True:
                        log["detect"].append(decoded) or loc.ImageOutcome(status="detected"))
    monkeypatch.setattr(loc, "record_scene_skip",
                        lambda iid, ctx, d, scene_version, top_label, job_id=None:
                        log["skip"].append((scene_version, top_label)) or loc.ImageOutcome(status="disabled"))
    monkeypatch.setattr(sr, "save_scene_label", lambda iid, result, **kw: log["saved"].append(result.top_label))
    for name in ("ok.jpg", "broken.jpg"):
        (tmp_path / name).write_bytes(b"x")
    log["decoded"], log["dir"] = decoded, tmp_path
    return log


def _router(classifier, thresholds):
    router = lr.SceneRouter.__new__(lr.SceneRouter)
    router.backend, router.thresholds, router.classifier = "test", thresholds, classifier
    return router


def _run(router, calls, name="ok.jpg"):
    return router.localize(1, str(calls["dir"] / name), ctx=None, max_regions=10, job_id=5)


def test_bird_scene_runs_detector_on_the_same_decode(calls):
    assert _run(_router(_Classifier(bird=0.4), {"wildlife_bird": 0.3}), calls).status == "detected"
    assert calls["decode"] == 1 and calls["detect"] == [calls["decoded"]] and calls["saved"] == ["landscape"]


def test_below_threshold_records_a_scene_route_skip(calls):
    assert _run(_router(_Classifier(bird=0.1), {"wildlife_bird": 0.3}), calls).status == "disabled"
    assert calls["skip"] == [("scene_v2/test/abc", "landscape")] and calls["detect"] == []


def test_uncalibrated_route_and_classifier_failure_fail_open(calls):
    _run(_router(_Classifier(bird=0.0), {}), calls)
    _run(_router(_Classifier(error=RuntimeError("cuda")), {"wildlife_bird": 0.3}), calls)
    assert calls["detect"] == [calls["decoded"], calls["decoded"]] and calls["skip"] == []


def test_decode_failure_and_missing_file_go_through_localize_image(calls):
    _run(_router(_Classifier(bird=0.0), {"wildlife_bird": 0.3}), calls, "broken.jpg")
    _run(_router(_Classifier(bird=0.0), {"wildlife_bird": 0.3}), calls, "missing.jpg")
    assert calls["detect"] == [None, None] and calls["skip"] == [] and calls["saved"] == []


def test_scene_route_is_off_by_default(monkeypatch):
    from modules import config

    monkeypatch.setattr(config, "get_config_section", lambda name: {})
    assert sr.scene_route_settings() == {"enabled": False, "backend": "hf_clip_b32", "run_thresholds": {}}


# --- #809: every lane goes through the scene route when it is on ---

def test_a_given_decode_is_reused_and_job_id_is_optional(calls):
    router = _router(_Classifier(bird=0.4), {"wildlife_bird": 0.3})
    out = router.localize(1, str(calls["dir"] / "ok.jpg"), None, max_regions=10, decoded=calls["decoded"])
    assert out.status == "detected" and calls["decode"] == 0 and calls["detect"] == [calls["decoded"]]


def test_a_given_decode_still_records_the_scene_skip(calls):
    router = _router(_Classifier(bird=0.1), {"wildlife_bird": 0.3})
    out = router.localize(1, str(calls["dir"] / "ok.jpg"), None, max_regions=10, decoded=calls["decoded"])
    assert out.status == "disabled" and calls["decode"] == 0 and calls["skip"] and calls["detect"] == []


def test_localize_routed_without_a_router_goes_straight_to_the_detector(calls):
    out = lr.localize_routed(None, 1, str(calls["dir"] / "ok.jpg"), None, max_regions=10, decoded=calls["decoded"])
    assert out.status == "detected" and calls["detect"] == [calls["decoded"]] and calls["saved"] == []


def test_localize_routed_with_a_router_classifies_first(calls):
    router = _router(_Classifier(bird=0.1), {"wildlife_bird": 0.3})
    out = lr.localize_routed(router, 1, str(calls["dir"] / "ok.jpg"), None, max_regions=10)
    assert out.status == "disabled" and calls["saved"] == ["landscape"] and calls["detect"] == []


def test_scene_router_or_none_follows_the_config(monkeypatch):
    monkeypatch.setattr(lr, "scene_route_settings", lambda: {"enabled": False, "backend": "x", "run_thresholds": {}})
    assert lr.scene_router_or_none() is None
    monkeypatch.setattr(lr, "scene_route_settings", lambda: {"enabled": True, "backend": "x", "run_thresholds": {}})
    monkeypatch.setattr(lr, "SceneRouter", lambda settings: ("router", settings["backend"]))
    assert lr.scene_router_or_none() == ("router", "x")


@pytest.mark.parametrize("script", ["scripts/backfill_region_keypoints.py",
                                    "scripts/maintenance/shadow_rescan_bird_v1_misses.py"])
def test_direct_detector_callers_now_go_through_the_route(script):
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / script).read_text(encoding="utf-8")
    assert "localize_routed(" in source and "scene_router_or_none(" in source
    assert "localize_image(" not in source
