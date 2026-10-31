"""Versioned numerical diagnostics in display-luma units; no ranking side effects."""
from __future__ import annotations

import math
import cv2
import numpy as np

EXTRACTOR_VERSION = "diagnostics-2.1"
CELL_SIZE = 64
PEAK_TILE = 512
MAD_NORMAL = 0.6744897501960817
# Fixed display scales, shared across images; not calibrated quality grades.
FOCUS_DISPLAY_SCALE = .12
NOISE_DISPLAY_SCALE = .08
OUTLINE_FLOOR = .012
TEXTURE_FLOOR = .010


def _shape(image):
    return (image.height, image.width) if hasattr(image, "crop") else image.shape[:2]


def _grey(image, box=None):
    if hasattr(image, "crop"):
        data = np.asarray((image.crop(box) if box else image).convert("L"))
    else:
        data = image if box is None else image[box[1]:box[3], box[0]:box[2]]
        if data.ndim == 3:
            data = cv2.cvtColor(data, cv2.COLOR_RGB2GRAY)
    result = data.astype(np.float32)
    if np.issubdtype(data.dtype, np.integer):
        result /= np.iinfo(data.dtype).max
    return result


def noise_sigma(grey):
    """Haar diagonal-band MAD on low-structure pixels; reject correlated texture."""
    h, w = grey.shape
    h, w = h // 2 * 2, w // 2 * 2
    if min(h, w) < 8:
        return None
    a = grey[:h:2, :w:2]
    b = grey[:h:2, 1:w:2]
    c = grey[1:h:2, :w:2]
    d = grey[1:h:2, 1:w:2]
    detail = (a - b - c + d) / 2
    smooth = cv2.GaussianBlur(grey, (0, 0), 1.2)
    gx = cv2.Scharr(smooth, cv2.CV_32F, 1, 0) / 32
    gy = cv2.Scharr(smooth, cv2.CV_32F, 0, 1) / 32
    structure = np.hypot(gx, gy)[:h:2, :w:2]
    keep = structure < .02
    samples = detail[keep]
    if samples.size < 16:
        return None
    for x, y in ((detail[:, :-1], detail[:, 1:]), (detail[:-1], detail[1:])):
        if x.size >= 16 and np.std(x) > 1e-5 and np.std(y) > 1e-5:
            correlation = float(np.corrcoef(x.ravel(), y.ravel())[0, 1])
            if abs(correlation) > .35:
                return None
    median = np.median(samples)
    return float(np.median(np.abs(samples - median)) / MAD_NORMAL)


def sharpness(grey, sigma=None):
    if min(grey.shape) < 3:
        return None
    lap = cv2.Laplacian(grey, cv2.CV_32F, ksize=1)[1:-1, 1:-1]
    # The 4-neighbour Laplacian has sum-of-squared coefficients 20.
    return math.sqrt(max(0.0, float(np.var(lap)) - 20 * (sigma or 0.0) ** 2))


def compute_maps(image, *, cancelled=lambda: False):
    height, width = _shape(image)
    xs, ys = list(range(0, width, CELL_SIZE)) + [width], list(range(0, height, CELL_SIZE)) + [height]
    focus_values, noise_values = [], []
    for y0, y1 in zip(ys, ys[1:]):
        if cancelled():
            raise InterruptedError()
        for x0, x1 in zip(xs, xs[1:]):
            patch = _grey(image, (x0, y0, x1, y1))
            sigma = noise_sigma(patch)
            focus_values.append(sharpness(patch, sigma))
            noise_values.append(sigma)
    def grid(values, scale, units):
        return {"cells_x": len(xs) - 1, "cells_y": len(ys) - 1, "cell_size_px": CELL_SIZE,
                "x_edges": xs, "y_edges": ys, "values": values,
                "values_normalized": [None if value is None else min(1.0, max(0.0, value / scale)) for value in values],
                "units": units, "normalization": "fixed_display_scale", "display_scale": scale}
    return {"sharpness": grid(focus_values, FOCUS_DISPLAY_SCALE, "noise_corrected_laplacian_rms"),
            "noise": grid(noise_values, NOISE_DISPLAY_SCALE, "display_luma_sigma")}


def peaking_fields(image, *, cancelled=lambda: False):
    height, width = _shape(image)
    outputs = {mode: np.zeros((height, width), np.uint8) for mode in ("outlines", "texture", "both")}
    halo = 12
    for y in range(0, height, PEAK_TILE):
        for x in range(0, width, PEAK_TILE):
            if cancelled():
                raise InterruptedError()
            x0, y0 = max(0, x - halo), max(0, y - halo)
            x1, y1 = min(width, x + PEAK_TILE + halo), min(height, y + PEAK_TILE + halo)
            grey = _grey(image, (x0, y0, x1, y1))
            sigma = noise_sigma(grey) or 0.0
            smooth = cv2.GaussianBlur(grey, (0, 0), 1.0)
            gx = cv2.Scharr(smooth, cv2.CV_32F, 1, 0) / 32
            gy = cv2.Scharr(smooth, cv2.CV_32F, 0, 1) / 32
            edges = np.hypot(gx, gy)
            detail = np.abs(cv2.GaussianBlur(grey, (0, 0), .6) - cv2.GaussianBlur(grey, (0, 0), 1.6))
            edge_floor, texture_floor = max(OUTLINE_FLOOR, sigma * .85), max(TEXTURE_FLOOR, sigma * 1.5)
            outlines = np.clip((edges - edge_floor) / .12, 0, 1)
            texture = np.clip((detail - texture_floor) / .10, 0, 1)
            region = (slice(y - y0, min(height, y + PEAK_TILE) - y0), slice(x - x0, min(width, x + PEAK_TILE) - x0))
            destination = (slice(y, min(height, y + PEAK_TILE)), slice(x, min(width, x + PEAK_TILE)))
            for mode, field in (("outlines", outlines), ("texture", texture), ("both", np.maximum(outlines, texture))):
                outputs[mode][destination] = np.round(field[region] * 255).astype(np.uint8)
    return outputs


def measure_head(image, points, region):
    height, width = _shape(image)
    x0, y0, x1, y1 = region
    reliable = {p["name"]: p for p in points if p.get("confidence", 0) >= .8
                and p.get("visible", True) and x0 <= p.get("x", -1) <= x1 and y0 <= p.get("y", -1) <= y1}
    eyes = [reliable[name] for name in ("left_eye", "right_eye") if name in reliable]
    anchors = eyes + [reliable[name] for name in ("beak", "head_top") if name in reliable]
    if not eyes or len(anchors) < 2:
        return {"state": "unavailable", "reason": "Reliable eyes and head landmarks are required"}
    xs, ys = [p["x"] for p in anchors], [p["y"] for p in anchors]
    pad = max(max(xs) - min(xs), max(ys) - min(ys)) * .25
    head = (max(x0, min(xs) - pad), max(y0, min(ys) - pad), min(x1, max(xs) + pad), min(y1, max(ys) + pad))
    px = (int(head[0] * width), int(head[1] * height), max(int(head[0] * width) + 1, int(head[2] * width)), max(int(head[1] * height) + 1, int(head[3] * height)))
    patch = _grey(image, px)
    head_sharpness = sharpness(patch, noise_sigma(patch))
    small = px[2] - px[0] < 16 or px[3] - px[1] < 16
    side = max(16, round((px[2] - px[0]) * .35))
    measurements = []
    for point in eyes:
        cx, cy = round(point["x"] * width), round(point["y"] * height)
        eye = _grey(image, (max(0, cx - side // 2), max(0, cy - side // 2), min(width, cx + side // 2), min(height, cy + side // 2)))
        value = sharpness(eye, noise_sigma(eye))
        ratio = value / head_sharpness if not small and value is not None and head_sharpness and head_sharpness > 1e-6 else None
        measurements.append({"name": point["name"], "x": point["x"], "y": point["y"], "sharpness_ratio": ratio,
                             "evidence_confidence": point["confidence"], "limitation": "small_head" if small else "low_contrast" if ratio is None else None})
    facing = None
    if "beak" in reliable:
        facing = {"x1": float(np.mean([p["x"] for p in eyes])), "y1": float(np.mean([p["y"] for p in eyes])),
                  "x2": reliable["beak"]["x"], "y2": reliable["beak"]["y"]}
    return {"head_bbox": list(head), "facing_vector": facing, "eyes": measurements, "scope": "primary_head"}
