import queue
import threading

from modules.phases import PhaseCode
from modules.pipeline import ImageJob, ScoringWorker


class _DummyScorer:
    VERSION = "test"

    def preprocess_image(self, *_args, **_kwargs):
        raise AssertionError("preprocess_image should not be called when scoring phase is not targeted")

    def run_all_models(self, *_args, **_kwargs):
        raise AssertionError("run_all_models should not be called when scoring phase is not targeted")


def test_scoring_worker_skips_when_scoring_not_targeted():
    input_q = queue.Queue()
    output_q = queue.Queue()
    stop_event = threading.Event()
    worker = ScoringWorker(input_q, output_q, stop_event, _DummyScorer())

    job = ImageJob(
        image_path="D:/does/not/matter.jpg",
        job_id=123,
        target_phases=[PhaseCode.INDEXING.value, PhaseCode.METADATA.value],
    )

    worker.process(job)

    processed = output_q.get_nowait()
    assert processed is job
    assert processed.status == "skipped"
