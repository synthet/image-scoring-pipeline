"""Spec 08 (#780): the shadow runner stores bird_agreement runs (AC-1 to AC-3, AC-6, AC-10 to AC-12)."""

from types import SimpleNamespace

from PIL import Image

import modules.localization as loc
import modules.localization_agreement_runner as ar

BIRD = {"id": 5, "status": "detected", "detector_config_hash": "y", "source_hash": "s", "source_hash_version": "1",
        "rendition_hash": "r", "rendition_version": "1", "orientation": 1, "display_width": 1000,
        "display_height": 500, "decode_route": "raw_embedded_preview"}
REGIONS = [{"id": 11, "rank": 0, "x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3},
           {"id": 12, "rank": 1, "x1": 0.5, "y1": 0.5, "x2": 0.7, "y2": 0.7}]


class _Conn:
    def __init__(self, bird=BIRD, latest=None, regions=REGIONS, selected=None):
        self.bird, self.latest, self.regions, self.selected = bird, latest, regions, selected

    def query_one(self, sql, params):
        if "image_localization_selections" in sql:
            return self.selected
        return self.bird if params[1] == "bird" else self.latest

    def query(self, sql, params):
        return self.regions


class _RTMDet:
    enabled = True
    version = "v"
    config_hash = "rt"

    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def detect(self, image):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return [{"region": (0.17, 0.17, 0.83, 0.83), "conf": 0.42, "cls": "bird"}]


def _setup(monkeypatch, conn, rendition="r"):
    written = []
    monkeypatch.setattr("modules.db.get_connector", lambda: conn)
    def write(run, regions, publish=True):
        assert publish is False and run["is_current"] is False  # AC-13
        written.append((run, regions))
        return 1

    monkeypatch.setattr(loc, "write_run", write)
    monkeypatch.setattr(loc, "decode_for_localization", lambda path: SimpleNamespace(
        image=Image.new("RGB", (1000, 500)), descriptor=SimpleNamespace(rendition_hash=rendition)))
    return written


def _ctx(rtmdet=None):
    return ar.AgreementContext(rtmdet=rtmdet or _RTMDet())


def test_disabled_loads_no_model(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("RTMDet loaded while disabled")

    monkeypatch.setattr("modules.detectors.rtmdet.load_rtmdet", boom)
    assert ar.load_agreement_context({}) is None
    assert ar.load_agreement_context({"agreement": {"enabled": False}}) is None


def test_writes_only_agreement_rows(monkeypatch):
    written = _setup(monkeypatch, _Conn())
    assert ar.score_image(1, "x.nef", _ctx()) == "detected"
    assert len(written) == 1
    run, _regions = written[0]
    assert run["detector_key"] == "bird_agreement" and run["status"] == "detected"


def test_scores_every_region(monkeypatch):
    written = _setup(monkeypatch, _Conn())
    rt = _RTMDet()
    ar.score_image(1, "x.nef", _ctx(rt))
    regions = written[0][1]
    assert rt.calls == 2
    assert [r["rank"] for r in regions] == [0, 1]
    assert [r["provider_class_id"] for r in regions] == ["agree:region:11", "agree:region:12"]
    assert regions[0]["conf"] == 0.42 and regions[0]["region"] == (0.1, 0.1, 0.3, 0.3)


def test_no_detected_bird_run_is_skipped(monkeypatch):
    written = _setup(monkeypatch, _Conn(bird={**BIRD, "status": "no_detection"}))
    assert ar.score_image(1, "x.nef", _ctx()) is None
    assert written == []


def test_skips_unchanged_image(monkeypatch):
    hash_ = ar.agreement_config_hash("rt", "y")
    latest = {"status": "detected", "detector_config_hash": hash_, "rendition_hash": "r", "source_hash": "s"}
    written = _setup(monkeypatch, _Conn(latest=latest))
    assert ar.score_image(1, "x.nef", _ctx()) is None
    assert written == []


def test_retryable_attempt_is_tried_again(monkeypatch):
    hash_ = ar.agreement_config_hash("rt", "y")
    latest = {"status": "retryable_error", "detector_config_hash": hash_, "rendition_hash": "r", "source_hash": "s"}
    written = _setup(monkeypatch, _Conn(latest=latest))
    assert ar.score_image(1, "x.nef", _ctx()) == "detected"
    assert len(written) == 1


def test_force_rescoring_ignores_unchanged(monkeypatch):
    hash_ = ar.agreement_config_hash("rt", "y")
    latest = {"status": "detected", "detector_config_hash": hash_, "rendition_hash": "r", "source_hash": "s"}
    written = _setup(monkeypatch, _Conn(latest=latest))
    assert ar.score_image(1, "x.nef", _ctx(), force=True) == "detected"
    assert len(written) == 1


def test_failure_records_retryable_and_continues(monkeypatch):
    written = _setup(monkeypatch, _Conn())
    assert ar.score_image(1, "x.nef", _ctx(_RTMDet(fail=True))) == "retryable_error"
    run, regions = written[0]
    assert run["status"] == "retryable_error" and run["is_retryable"] is True and regions == []


def test_rendition_mismatch_is_retryable(monkeypatch):
    written = _setup(monkeypatch, _Conn(), rendition="other")
    assert ar.score_image(1, "x.nef", _ctx()) == "retryable_error"
    assert written[0][0]["status"] == "retryable_error"


def test_selected_region_is_appended(monkeypatch):
    selected = {"region_id": 99, "rendition_hash": "r", "x1": 0.2, "y1": 0.2, "x2": 0.4, "y2": 0.4}
    written = _setup(monkeypatch, _Conn(selected=selected))
    ar.score_image(1, "x.nef", _ctx())
    last = written[0][1][-1]
    assert last["rank"] == 2 and last["provider_class_id"] == "agree:selected:99"


def test_selected_region_on_the_current_run_is_not_duplicated(monkeypatch):
    selected = {"region_id": 11, "rendition_hash": "r", "x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}
    written = _setup(monkeypatch, _Conn(selected=selected))
    ar.score_image(1, "x.nef", _ctx())
    assert len(written[0][1]) == 2


def test_selected_region_on_another_rendition_is_retryable(monkeypatch):
    selected = {"region_id": 99, "rendition_hash": "old", "x1": 0.2, "y1": 0.2, "x2": 0.4, "y2": 0.4}
    written = _setup(monkeypatch, _Conn(selected=selected))
    assert ar.score_image(1, "x.nef", _ctx()) == "retryable_error"
    assert written[0][1] == []


def test_dry_run_writes_nothing(monkeypatch):
    written = _setup(monkeypatch, _Conn())
    assert ar.score_image(1, "x.nef", _ctx(), dry_run=True) == "detected"
    assert written == []


def test_report_counts_and_denominators():
    rows = [{"shoot": "a", "score": 0.5, "eyes": 2}, {"shoot": "a", "score": 0.0, "eyes": 1},
            {"shoot": "a", "score": 0.09, "eyes": 0}, {"shoot": "b", "score": 0.1, "eyes": 1}]
    table = ar.summarize_shoots(rows, limit=0.10)
    assert table["a"] == {"regions": 3, "at_or_above": 1, "below": 2, "eyes": 3, "eyes_below": 1}
    assert table["b"] == {"regions": 1, "at_or_above": 1, "below": 0, "eyes": 1, "eyes_below": 0}


def test_limit_applies_at_read_time():
    rows = [{"shoot": "a", "score": 0.3, "eyes": 2}]
    assert ar.summarize_shoots(rows, limit=0.10)["a"]["below"] == 0
    assert ar.summarize_shoots(rows, limit=0.50)["a"]["below"] == 1
