"""Local blind reviewer. Serves only review units and allowlisted image previews."""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from modules.score_analytics import study
from modules.score_analytics.study_data import read_json


def serve(root: Path, *, host="127.0.0.1", port=7862, backend="http://127.0.0.1:7860"):
    sample = read_json(root / "sample.json")
    snapshot = read_json(root / "snapshot.json.gz")
    units = {u["id"]: u for u in sample["units"]}
    allowed = {i for u in units.values() for i in u["image_ids"]}
    paths = {r["id"]: r["path"] for r in snapshot["images"] if r["id"] in allowed}
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    page = (Path(__file__).with_name("study_review.html")).read_text(encoding="utf-8")
    page = page.replace("__CSRF_TOKEN__", token)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, payload, content_type="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            if url.path == "/":
                return self.send(200, page.encode(), "text/html; charset=utf-8")
            if url.path == "/api/units":
                return self.send(200, {"study_id": sample["study_id"], "units": [study.blind_unit(u) for u in units.values()]})
            if url.path == "/api/reviews":
                reviewer = urllib.parse.parse_qs(url.query).get("reviewer", [""])[0]
                with lock:
                    records = [json.loads(line) for line in (root / "reviews.jsonl").read_text(encoding="utf-8").splitlines() if line]
                return self.send(200, [r for r in records if r["reviewer"] == reviewer])
            if url.path.startswith("/image/"):
                try:
                    iid = int(url.path.rsplit("/", 1)[-1])
                    if iid not in paths:
                        return self.send(404, {"error": "Unknown review image"})
                    remote = backend.rstrip("/") + "/api/raw-preview?" + urllib.parse.urlencode({"path": paths[iid]})
                    with urllib.request.urlopen(remote, timeout=120) as response:
                        content_type = response.headers.get_content_type()
                        if not content_type.startswith("image/"):
                            raise ValueError("Backend did not return an image")
                        return self.send(200, response.read(), content_type)
                except Exception as exc:
                    logging.warning("Preview failed: %s", type(exc).__name__)
                    return self.send(502, {"error": "Preview unavailable; skip this unit or retry"})
            return self.send(404, {"error": "Not found"})

        def do_POST(self):
            if self.path != "/api/reviews" or self.headers.get("X-Study-Token") != token:
                return self.send(403, {"error": "Invalid review request"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Invalid review size")
                record = json.loads(self.rfile.read(length))
                unit = units.get(record.get("unit_id"))
                if unit is None:
                    raise ValueError("Unknown review unit")
                study.validate_review(unit, record)
                record["study_id"] = sample["study_id"]
                record["saved_at"] = datetime.now(timezone.utc).isoformat()
                with lock, (root / "reviews.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, allow_nan=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                self.send(200, {"saved": True})
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, {"error": str(exc)})

    logging.info("Blind review ready at http://%s:%s", host, port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
