import threading
import time
import pytest

from PIL import Image

from modules.visual_evidence.jobs import DiagnosticManager


def context(tmp_path, image_id=1):
    path = tmp_path / "source.png"
    if not path.exists():
        Image.new("RGB", (96, 64), "gray").save(path)
    return {"image_id": image_id, "path": str(path), "source_hash": "source-v1", "source_hash_version": "test", "region": None, "keypoints": [], "region_id": None, "keypoint_run_id": None}


def ready(manager, image_id, layer):
    for _ in range(100):
        manifest = manager.manifest(image_id)
        if manifest["layers"][layer]["state"] not in ("queued", "running"):
            return manifest
        time.sleep(.02)
    raise AssertionError("diagnostic job did not finish")


def test_duplicate_requests_share_work_and_cancellation_is_subscription_scoped(tmp_path):
    gate, entered = threading.Event(), threading.Event()
    calls = []
    def compute(layer, prepared, ctx):
        calls.append(layer)
        entered.set()
        gate.wait(3)
        return {"measurements": {"value": 1}, "artifacts": {}}
    with DiagnosticManager(tmp_path / "cache", context_loader=lambda image_id: context(tmp_path, image_id), computer=compute) as manager:
        first = manager.request(1, ["sharpness"])
        assert entered.wait(3)
        manager.request(1, ["sharpness"])
        assert manager.cancel(1, first["request_id"])
        gate.set()
        manifest = ready(manager, 1, "sharpness")
        assert manifest["layers"]["sharpness"]["state"] == "ready"
        assert calls == ["sharpness"]
        manager.request(1, ["sharpness"])
        assert calls == ["sharpness"]
        assert manifest["rendition"]["display_width"] == 96


def test_identity_change_hides_old_results_and_missing_source_is_honest(tmp_path):
    current = context(tmp_path)
    with DiagnosticManager(tmp_path / "cache", context_loader=lambda _: dict(current), computer=lambda *args: {"artifacts": {}}) as manager:
        manager.request(1, ["noise"])
        assert ready(manager, 1, "noise")["layers"]["noise"]["state"] == "ready"
        current["source_hash"] = "source-v2"
        assert manager.manifest(1)["layers"]["noise"]["state"] == "not_requested"
        current["path"] = str(tmp_path / "gone.png")
        result = manager.request(1, ["noise"])
        assert result["layers"]["noise"]["state"] == "unavailable"
        assert not result["layers"]["noise"].get("artifacts")


def test_mask_waits_for_scoring_while_cpu_work_can_finish(tmp_path):
    busy = threading.Event()
    busy.set()
    computed = []
    with DiagnosticManager(tmp_path / "cache", context_loader=lambda image_id: context(tmp_path, image_id), computer=lambda layer, *args: (computed.append(layer) or {"artifacts": {}}), gpu_busy=busy.is_set) as manager:
        manager.request(1, ["mask", "sharpness"])
        assert ready(manager, 1, "sharpness")["layers"]["sharpness"]["state"] == "ready"
        assert "mask" not in computed
        busy.clear()
        assert ready(manager, 1, "mask")["layers"]["mask"]["state"] == "ready"


@pytest.mark.parametrize("completed", [False, True])
def test_last_subscriber_releases_job_and_source_lock_bookkeeping(tmp_path, completed):
    gate, entered = threading.Event(), threading.Event()
    def compute(*args):
        entered.set()
        gate.wait(3)
        return {"artifacts": {}}
    with DiagnosticManager(tmp_path / "cache", context_loader=lambda image_id: context(tmp_path, image_id), computer=compute) as manager:
        request = manager.request(1, ["noise"])
        assert entered.wait(3)
        future = next(iter(manager._jobs.values()))["future"]
        if completed:
            gate.set()
            future.result(3)
        assert manager.cancel(1, request["request_id"])
        gate.set()
        future.result(3)
        assert not manager._requests
        assert not manager._jobs
        assert not manager._source_locks
