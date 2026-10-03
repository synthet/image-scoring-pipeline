"""The blind review page and its server work together (#496). No database, no backend images."""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from modules.score_analytics import study_review
from modules.score_analytics.study_data import write_json


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path: Path):
    units = [
        {"id": "u-single", "kind": "single", "image_ids": [1], "stratum": "secret", "split": "test", "weight": 3.0},
        {"id": "u-burst", "kind": "burst", "image_ids": [2, 3], "stratum": "secret", "split": "train", "weight": 1.0},
    ]
    write_json(tmp_path / "sample.json", {"study_id": "study-x", "units": units})
    write_json(tmp_path / "snapshot.json.gz", {"images": [{"id": i, "path": f"/p/{i}.jpg"} for i in (1, 2, 3)]})
    (tmp_path / "reviews.jsonl").touch()
    port = _free_port()
    threading.Thread(target=study_review.serve, args=(tmp_path,), kwargs={"port": port}, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/api/units", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    return base, tmp_path


def _get(url: str):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode()


def _post(base: str, record: dict, token: str):
    req = urllib.request.Request(base + "/api/reviews", data=json.dumps(record).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Study-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _token(page: str) -> str:
    return page.split('const TOKEN = "', 1)[1].split('"', 1)[0]


def test_page_is_served_with_a_token_and_no_placeholder(server):
    base, _ = server
    page = _get(base + "/")
    assert "__CSRF_TOKEN__" not in page and len(_token(page)) >= 32
    for endpoint in ("/api/units", "/api/reviews", "/image/", "X-Study-Token", "human_blind"):
        assert endpoint in page


def test_units_are_blind(server):
    base, _ = server
    data = json.loads(_get(base + "/api/units"))
    assert data["study_id"] == "study-x"
    assert all(set(u) == {"id", "kind", "image_ids"} for u in data["units"])


def test_valid_records_are_saved_and_listed_per_reviewer(server):
    base, root = server
    token = _token(_get(base + "/"))
    single = {"unit_id": "u-single", "reviewer": "owner", "status": "done", "source": "human_blind",
              "ratings": {"general": 4, "technical": 3, "aesthetic": 5}, "elapsed_ms": 1200}
    burst = {"unit_id": "u-burst", "reviewer": "owner", "status": "done", "source": "human_blind",
             "frames": [{"image_id": 2, "grade": 2, "best": True}, {"image_id": 3, "grade": 0, "best": False}]}
    assert _post(base, single, token) == (200, {"saved": True})
    assert _post(base, burst, token) == (200, {"saved": True})
    assert _post(base, {**single, "unit_id": "u-burst", "status": "skipped"}, token)[0] == 200
    listed = json.loads(_get(base + "/api/reviews?reviewer=owner"))
    assert [r["unit_id"] for r in listed] == ["u-single", "u-burst", "u-burst"]
    assert json.loads(_get(base + "/api/reviews?reviewer=someone-else")) == []
    assert len((root / "reviews.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_invalid_records_and_bad_tokens_are_rejected(server):
    base, root = server
    token = _token(_get(base + "/"))
    no_best = {"unit_id": "u-burst", "reviewer": "owner", "status": "done", "source": "human_blind",
               "frames": [{"image_id": 2, "grade": 1, "best": False}, {"image_id": 3, "grade": 0, "best": False}]}
    assert _post(base, no_best, token)[0] == 400
    half_rated = {"unit_id": "u-single", "reviewer": "owner", "status": "done", "source": "human_blind",
                  "ratings": {"general": 4}}
    assert _post(base, half_rated, token)[0] == 400
    assert _post(base, {**half_rated, "status": "skipped"}, "wrong-token")[0] == 403
    assert (root / "reviews.jsonl").read_text(encoding="utf-8") == ""


def test_unknown_image_is_refused_without_contacting_the_backend(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base + "/image/999")
    assert e.value.code == 404
