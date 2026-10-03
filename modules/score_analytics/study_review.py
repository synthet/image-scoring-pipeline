"""Local blind reviewer. Serves only review units and allowlisted image previews."""
from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from modules.score_analytics import study
from modules.score_analytics.study_data import read_json


RAW_SUFFIXES = {".nef", ".nrw", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".rw2", ".raf", ".pef", ".srw"}
#: LibRaw ``sizes.flip`` -> PIL rotation (degrees counter-clockwise). flip 5 verified pixel-exact
#: against modules.localization.decode_for_localization on portrait NEFs.
FLIP_ROTATION = {3: 180, 5: 90, 6: -90}
PREVIEW_LONG_EDGE = 2048
BACKEND_RETRY_S = 60


def local_path(path: str) -> str:
    """``/mnt/<drive>/...`` snapshot paths -> ``<DRIVE>:/...`` when running on Windows."""
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", path)
    return f"{m.group(1).upper()}:/{m.group(2)}" if m and os.name == "nt" else path


def local_preview(path: str, long_edge: int = PREVIEW_LONG_EDGE) -> bytes:
    """Display-oriented JPEG preview without the WebUI: embedded RAW JPEG (rawpy) or the image itself."""
    from PIL import Image, ImageOps

    target = local_path(path)
    if Path(target).suffix.lower() in RAW_SUFFIXES:
        import rawpy

        with rawpy.imread(target) as raw:
            thumb, flip = raw.extract_thumb(), raw.sizes.flip
        if thumb.format == rawpy.ThumbFormat.JPEG:
            img = Image.open(io.BytesIO(thumb.data))
        else:
            img = Image.fromarray(thumb.data)
        if flip in FLIP_ROTATION:
            img = img.rotate(FLIP_ROTATION[flip], expand=True)
    else:
        img = ImageOps.exif_transpose(Image.open(target))
    img = img.convert("RGB")
    img.thumbnail((long_edge, long_edge))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def serve(root: Path, *, host="127.0.0.1", port=7862, backend="http://127.0.0.1:7860"):
    sample = read_json(root / "sample.json")
    snapshot = read_json(root / "snapshot.json.gz")
    units = {u["id"]: u for u in sample["units"]}
    allowed = {i for u in units.values() for i in u["image_ids"]}
    paths = {r["id"]: r["path"] for r in snapshot["images"] if r["id"] in allowed}
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    # After a backend failure, skip it for BACKEND_RETRY_S: on Windows a refused localhost
    # connection takes ~2 s, which would otherwise be paid for every preview.
    backend_down_until = [0.0]
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
                except ValueError:
                    return self.send(404, {"error": "Unknown review image"})
                if iid not in paths:
                    return self.send(404, {"error": "Unknown review image"})
                if time.monotonic() >= backend_down_until[0]:
                    try:
                        remote = backend.rstrip("/") + "/api/raw-preview?" + urllib.parse.urlencode({"path": paths[iid]})
                        with urllib.request.urlopen(remote, timeout=120) as response:
                            content_type = response.headers.get_content_type()
                            if not content_type.startswith("image/"):
                                raise ValueError("Backend did not return an image")
                            return self.send(200, response.read(), content_type)
                    except Exception as exc:
                        backend_down_until[0] = time.monotonic() + BACKEND_RETRY_S
                        logging.info("Backend preview failed (%s); using local previews for %ds",
                                     type(exc).__name__, BACKEND_RETRY_S)
                try:
                    return self.send(200, local_preview(paths[iid]), "image/jpeg")
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
