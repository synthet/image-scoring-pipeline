#!/usr/bin/env python3
"""CPU-only RAW route comparison; isolated workers, no DB/models/shared cache.

Reports decode and process time, pixel hashes, geometry, memory and pairwise pixel
differences. Fixed sensor policies: camera WB, sRGB, 8 bit, AHD, default auto-bright
and gamma; source orientation applied once after disabling decoder rotation.
Images are kept only in a TemporaryDirectory. Only the JSON report is persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

ROUTES = ("embedded_preview", "rawpy_half", "dcraw_emu_half", "rawpy_full", "dcraw_emu_full")
POLICY = {"camera_wb": True, "color_space": "sRGB", "bits": 8, "demosaic": "AHD",
          "auto_bright": True, "gamma": [2.222, 4.5], "decoder_rotation": False,
          "orientation": "source EXIF applied once", "embedded_preview": "camera-rendered pixels"}


def pixel_digest(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def pixel_metrics(a: Image.Image, b: Image.Image, edge: int = 512) -> dict:
    """Whole-frame comparison after resize, NOT crop registration or quality scoring."""
    target = (edge, max(1, round(edge * a.height / a.width)))
    aa = np.asarray(a.convert("RGB").resize(target, Image.Resampling.LANCZOS), dtype=np.float32)
    bb = np.asarray(b.convert("RGB").resize(target, Image.Resampling.LANCZOS), dtype=np.float32)
    delta = aa - bb
    equal_size = a.size == b.size
    return {"native_dimensions_equal": equal_size,
            "aspect_ratio_delta": round(abs(a.width / a.height - b.width / b.height), 6),
            "exact_pixels": equal_size and pixel_digest(a) == pixel_digest(b),
            "comparison_size": list(target),
            "mae_8bit": round(float(np.abs(delta).mean()), 4),
            "rmse_8bit": round(float(np.sqrt(np.square(delta).mean())), 4)}


def decode_route(route: str, source: str, *, dcraw: str | None, timeout: float) -> tuple[Image.Image, dict]:
    if route == "embedded_preview":
        from modules.thumbnails import extract_embedded_jpeg
        image = extract_embedded_jpeg(source, min_size=1000)
        if image is None:
            raise RuntimeError("no embedded JPEG extracted")
        return image.convert("RGB"), {"engine": "exiftool/dcraw embedded JPEG extraction"}
    if route.startswith("rawpy_"):
        import rawpy
        with rawpy.imread(source) as raw:
            rgb = raw.postprocess(half_size=route.endswith("half"), use_camera_wb=True,
                                  output_color=rawpy.ColorSpace.sRGB, output_bps=8,
                                  demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                                  gamma=(2.222, 4.5), user_flip=0)
        return Image.fromarray(rgb), {"engine": "rawpy", "version": rawpy.__version__,
                                      "libraw_version": list(rawpy.libraw_version)}
    if route.startswith("dcraw_emu_"):
        if not dcraw:
            raise FileNotFoundError("dcraw_emu not configured or on PATH")
        cmd = [dcraw, "-Z", "-"]
        if route.endswith("half"):
            cmd.append("-h")
        cmd += ["-w", "-o", "1", "-q", "3", "-t", "0", source]
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode:
            # The status is evidence; do not include raw native diagnostic dumps.
            raise RuntimeError(f"dcraw_emu exit {result.returncode}")
        image = Image.open(io.BytesIO(result.stdout))
        image.load()
        return image.convert("RGB"), {"engine": "dcraw_emu", "arguments": cmd[1:-1],
                                      "output_bytes": len(result.stdout)}
    raise ValueError(f"unknown route: {route}")


def _peak_rss(who: str) -> float | None:
    if who == "RUSAGE_SELF" and sys.platform.startswith("linux"):
        # getrusage.ru_maxrss can include memory inherited before exec. VmHWM is
        # tied to the current mm and measures this worker after exec instead.
        try:
            match = re.search(r"^VmHWM:\s+(\d+)\s+kB", Path("/proc/self/status").read_text(), re.MULTILINE)
            return round(int(match[1]) / 1024, 2) if match else None
        except OSError:
            return None
    try:
        import resource
        value = resource.getrusage(getattr(resource, who)).ru_maxrss
        return round(value / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)
    except (ImportError, AttributeError):
        return None


def worker(route: str, source: str, destination: str, dcraw: str | None, timeout: float) -> dict:
    from modules.thumbnails import read_orientation
    orientation = read_orientation(source) or 1
    t0 = time.perf_counter()
    image, details = decode_route(route, source, dcraw=dcraw, timeout=timeout)
    decode_s = time.perf_counter() - t0
    transforms = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
                  4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
                  6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
                  8: Image.Transpose.ROTATE_90}
    if orientation in transforms:
        image = image.transpose(transforms[orientation])
    result = {"status": "ok", "route": route, "decode_s": round(decode_s, 6),
              "dimensions": list(image.size), "orientation_applied": orientation,
              "pixel_sha256": pixel_digest(image), "engine": details,
              "python_peak_rss_mib": _peak_rss("RUSAGE_SELF"),
              "python_peak_rss_source": "proc_self_VmHWM" if sys.platform.startswith("linux") else "ru_maxrss",
              "decoder_child_peak_rss_mib": _peak_rss("RUSAGE_CHILDREN")}
    image.save(destination, "PNG")
    image.close()
    return result


def run_worker(route: str, source: Path, scratch: Path, *, timeout: float, dcraw: str | None) -> dict:
    output = scratch / f"{route}.png"
    cmd = [sys.executable, str(Path(__file__).resolve()), str(source), "--worker-route", route,
           "--worker-output", str(output), "--timeout", str(timeout)]
    if dcraw:
        cmd += ["--dcraw", dcraw]
    t0 = time.perf_counter()
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=os.name == "posix")
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # A stuck RAW worker may still own exiftool/dcraw descendants.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=5)
                if process.poll() is None:
                    process.kill()
            process.communicate()
            raise
        if process.returncode:
            return {"route": route, "status": "worker_error", "exit_code": process.returncode}
        report = json.loads(stdout)
        if report["status"] == "ok":
            report["image_path"] = str(output)
    except subprocess.TimeoutExpired:
        report = {"route": route, "status": "timeout"}
    except (OSError, ValueError) as exc:
        report = {"route": route, "status": "error", "error_type": type(exc).__name__}
    report["process_wall_s"] = round(time.perf_counter() - t0, 6)
    return report


def tool_identity(tool: str | None) -> dict | None:
    if not tool:
        return None
    path = Path(shutil.which(tool) or tool).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def compare(files: list[Path], *, routes: list[str], repeats: int, timeout: float,
            dcraw: str | None, identify: str | None) -> dict:
    from modules.raw_diagnostics import probe_raw_file
    result = {"schema_version": 1, "environment": {"platform": platform.platform(),
               "python": sys.version, "omp_threads": os.environ.get("OMP_NUM_THREADS"),
               "dcraw_emu": tool_identity(dcraw), "raw_identify": tool_identity(identify)},
              "policy": POLICY, "repeats": repeats,
              "limitations": ["Small warmed-cache CPU sample; no quality labels or model inference.",
                              "Decode time includes route setup; process wall includes Python startup and PNG output.",
                              "Pixel differences are whole-frame resized; crop offsets are not registered.",
                              "CPU affinity and other host workloads were not controlled.",
                              "Python and decoder child peak RSS are separate, not combined concurrent memory."],
              "images": []}
    with tempfile.TemporaryDirectory(prefix="raw-decode-compare-") as tmp:
        scratch = Path(tmp)
        for source in files:
            item = {"file": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "diagnostic": probe_raw_file(source, tool=identify, enabled=True), "routes": [], "pairs": []}
            representatives = {}
            for route in routes:
                samples = []
                for _ in range(repeats):
                    sample = run_worker(route, source, scratch, timeout=timeout, dcraw=dcraw)
                    image_path = sample.pop("image_path", None)
                    if image_path:
                        with Image.open(image_path) as img:
                            representatives[route] = img.copy()
                    samples.append(sample)
                good = [s for s in samples if s["status"] == "ok"]
                item["routes"].append({"route": route, "successes": len(good), "attempts": repeats,
                                       "median_decode_s": statistics.median(s["decode_s"] for s in good) if good else None,
                                       "samples": samples})
            for a, b in itertools.combinations(representatives, 2):
                item["pairs"].append({"a": a, "b": b, **pixel_metrics(representatives[a], representatives[b])})
            for image in representatives.values():
                image.close()
            result["images"].append(item)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--dcraw", default=os.environ.get("DCRAW_EMU_PATH") or shutil.which("dcraw_emu"))
    ap.add_argument("--identify", default=os.environ.get("RAW_IDENTIFY_PATH") or shutil.which("raw-identify"))
    ap.add_argument("--routes", nargs="+", choices=ROUTES, default=list(ROUTES))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds per isolated worker")
    ap.add_argument("--output", type=Path, help="JSON report (stdout if omitted)")
    ap.add_argument("--worker-route", choices=ROUTES, help=argparse.SUPPRESS)
    ap.add_argument("--worker-output", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.repeats < 1 or args.timeout <= 0:
        ap.error("repeats and timeout must be positive")
    if args.worker_route:
        try:
            report = worker(args.worker_route, str(args.files[0]), args.worker_output, args.dcraw, args.timeout)
        except Exception as exc:
            report = {"status": "unavailable" if isinstance(exc, (ImportError, FileNotFoundError)) else "error",
                      "route": args.worker_route, "error_type": type(exc).__name__,
                      "reason": str(exc)[:300]}
        print(json.dumps(report))
        return 0
    for path in args.files:
        if not path.is_file():
            ap.error(f"input is not a file: {path}")
    report = compare([p.resolve() for p in args.files], routes=args.routes, repeats=args.repeats,
                     timeout=args.timeout, dcraw=args.dcraw, identify=args.identify)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text, end="")
    # Failed decodes are study results; a report with no decoded images is unusable.
    return int(not any(r["successes"] for image in report["images"] for r in image["routes"]))


if __name__ == "__main__":
    raise SystemExit(main())
