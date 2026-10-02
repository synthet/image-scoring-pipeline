from types import SimpleNamespace

from modules import tagging_image_processor as processor


class _Engine:
    def __init__(self, *, tags=None, caption="") -> None:
        self.tags = tags or []
        self.caption = caption

    def predict_keywords(self, _path, _keywords):
        return self.tags

    def generate_caption(self, _path):
        return self.caption


class _Report:
    def __init__(self) -> None:
        self.after = []
        self.skips = []
        self.failures = []

    def record_after(self, *args, **kwargs) -> None:
        self.after.append((args, kwargs))

    def record_skip(self, *args, **kwargs) -> None:
        self.skips.append((args, kwargs))

    def record_failure(self, *args, **kwargs) -> None:
        self.failures.append((args, kwargs))


def _runner(engine):
    metadata_writes = []
    runner = SimpleNamespace(
        tagging_engine=engine,
        scorer=None,
        current_count=0,
        total_count=1,
        write_metadata=lambda *args, **kwargs: metadata_writes.append((args, kwargs)),
    )
    return runner, metadata_writes


def test_process_tagging_image_row_records_done_result(monkeypatch) -> None:
    runner, metadata_writes = _runner(_Engine(tags=[" birds ", "nature"], caption="A bird"))
    statuses = []
    field_updates = []
    monkeypatch.setattr(processor, "_embedding_persistence_flags", lambda: (False, False))
    monkeypatch.setattr(
        processor.db,
        "set_image_phase_status",
        lambda *args, **kwargs: statuses.append((args, kwargs)),
    )
    monkeypatch.setattr(
        processor.db,
        "update_image_fields_batch",
        lambda updates: field_updates.extend(updates),
    )
    report = _Report()
    folders = set()

    counts = processor.process_tagging_image_row(
        runner,
        {"id": 7, "file_path": "/photos/bird.jpg", "title": None, "description": None},
        app_version="test-app",
        tagger_version="test-tagger",
        custom_keywords=None,
        overwrite=False,
        generate_captions=True,
        generate_accessibility=False,
        job_id=19,
        report_collector=report,
        write_keyword_relevance=False,
        log=lambda *_args, **_kwargs: None,
        processed_count=0,
        skipped_count=0,
        processed_folders=folders,
    )

    assert counts == (1, 0)
    assert [call[0][2].value for call in statuses] == ["running", "done"]
    assert field_updates == [
        (7, {"title": "A bird", "description": "A bird", "keywords": "birds,nature"})
    ]
    assert folders == {"/photos"}
    assert len(metadata_writes) == 1
    assert len(report.after) == 1
    assert report.skips == []


def test_process_tagging_image_row_records_empty_result_as_skipped(monkeypatch) -> None:
    runner, metadata_writes = _runner(_Engine())
    statuses = []
    monkeypatch.setattr(processor, "_embedding_persistence_flags", lambda: (False, False))
    monkeypatch.setattr(
        processor.db,
        "set_image_phase_status",
        lambda *args, **kwargs: statuses.append((args, kwargs)),
    )
    report = _Report()

    counts = processor.process_tagging_image_row(
        runner,
        {"id": 8, "file_path": "/photos/empty.jpg"},
        app_version="test-app",
        tagger_version="test-tagger",
        custom_keywords=None,
        overwrite=False,
        generate_captions=False,
        generate_accessibility=False,
        job_id=20,
        report_collector=report,
        write_keyword_relevance=False,
        log=lambda *_args, **_kwargs: None,
        processed_count=0,
        skipped_count=0,
        processed_folders=set(),
    )

    assert counts == (0, 1)
    assert [call[0][2].value for call in statuses] == ["running", "skipped"]
    assert statuses[-1][1]["skip_reason"] == "no tags produced"
    assert metadata_writes == []
    assert len(report.skips) == 1
