import subprocess
import sys

import pytest

from modules.visual_evidence import providers


@pytest.mark.parametrize("action,state", [("cancel", "cancelled"), ("scoring", "deferred")])
def test_provider_terminates_child_when_cancelled_or_scoring_starts(monkeypatch, tmp_path, action, state):
    script = tmp_path / "slow.py"
    script.write_text("import time; time.sleep(30)")
    monkeypatch.setattr(providers, "mask_provider", lambda: {"available": True, "python": sys.executable, "script": str(script), "checkpoint": "unused"})
    processes = []
    original = subprocess.Popen
    def launch(*args, **kwargs):
        child = original(*args, **kwargs)
        processes.append(child)
        return child
    monkeypatch.setattr(providers.subprocess, "Popen", launch)
    result = providers.segment("unused", [0, 0, 1, 1], cancelled=lambda: action == "cancel", gpu_busy=lambda: action == "scoring")
    assert result == {"state": state}
    assert len(processes) == 1 and processes[0].poll() is not None


def test_unavailable_provider_does_not_launch_inference(monkeypatch):
    monkeypatch.setattr(providers, "mask_provider", lambda: {"available": False, "reason": "No local weights"})
    monkeypatch.setattr(providers.subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected model launch"))
    assert providers.segment("unused", [0, 0, 1, 1])["state"] == "unavailable"
