"""Failed image normalization must not send the uncorrected source to models."""
import queue
import threading
from types import SimpleNamespace

import pytest

from modules.pipeline import ImageJob, PrepWorker, ScoringWorker


@pytest.mark.parametrize("failure", ["none", "exception"])
def test_scoring_worker_fails_before_inference_when_preparation_fails(monkeypatch, failure):
    from modules import pipeline
    calls = []
    def preprocess(*_, **__):
        if failure == "exception":
            raise ValueError("undecodable input")
        return None
    def infer(*_, **__):
        calls.append("inference")
        return {}
    scorer = SimpleNamespace(preprocess_image=preprocess, run_all_models=infer)
    output = queue.Queue()
    worker = ScoringWorker(queue.Queue(), output, threading.Event(), scorer,
                           liqe_scorer=SimpleNamespace(predict=lambda _: calls.append("liqe")))
    monkeypatch.setattr(pipeline.app_config, "load_config", lambda: {})
    job = ImageJob(image_path="bad.jpg", process_path="bad.jpg", job_id=0)
    worker.process(job)
    assert output.get_nowait() is job
    assert calls == []
    assert job.status == "failed"
    assert job.error.startswith("Scoring preprocessing failed")


def test_prep_preserves_raw_decode_route_after_temporary_jpeg_conversion(tmp_path, monkeypatch):
    from modules import pipeline
    prepared = tmp_path / 'prepared.jpg'
    prepared.write_bytes(b'converted preview')
    converter = SimpleNamespace(convert_raw_to_jpeg=lambda _: str(prepared),
                                last_raw_conversion_route='exiftool:JpgFromRaw')
    worker = PrepWorker(queue.Queue(), queue.Queue(), threading.Event(),
                        SimpleNamespace(is_raw_file=lambda _: True))
    worker._raw_converter = converter
    temporary = tmp_path / 'temporary'
    temporary.mkdir()
    monkeypatch.setattr(pipeline.tempfile, 'mkdtemp', lambda **_: str(temporary))
    job = ImageJob('original.NEF', 0, thumbnail_path=str(prepared))
    assert worker._apply_scoring_prep(job)
    assert job.process_path == str(prepared)
    assert job.source_decode_route == 'exiftool:JpgFromRaw'
