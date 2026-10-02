"""Per-image RTMDet animal + small-box YOLO refine probe, shared by the v1 review scripts.

Candidates are kept down to confidence 0.05 so later rules can choose their own cut; the refine
pass mirrors the cascade (``refine_crop`` / ``REFINE_PAD_FRAC``) on boxes with conf >= 0.25 and
area < 0.02. Diagnostic only: nothing here writes to the database.
"""

from __future__ import annotations

PROBE_THRESHOLD = 0.05
REFINE_MIN_CONF = 0.25
REFINE_MAX_AREA = 0.02


def probe_image(img, rt, yolo) -> dict:
    """Return ``{"coco": [...], "refine": [...]}`` for an RGB PIL image in frame-normalized coordinates."""
    import numpy as np

    from modules.detectors.rtmdet import letterbox, select_animal_boxes
    from modules.localization_cascade import REFINE_PAD_FRAC, refine_crop

    w, h = img.size
    tensor, scale, px, py = letterbox(img, rt.mean, rt.std)
    outs = rt.session.run(None, {rt.session.get_inputs()[0].name: tensor})
    boxes = (np.asarray(outs[0])[0].astype(np.float64) - [px, py, px, py]) / scale
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
    coco = select_animal_boxes(boxes, np.asarray(outs[1])[0], w, h,
                               threshold=PROBE_THRESHOLD, retry_threshold=PROBE_THRESHOLD)
    refined = []
    for box in coco:
        region = box["region"]
        area = (region[2] - region[0]) * (region[3] - region[1])
        if box["conf"] < REFINE_MIN_CONF or area >= REFINE_MAX_AREA:
            continue
        crop_box = refine_crop(region, REFINE_PAD_FRAC)
        crop = img.crop((int(crop_box[0] * w), int(crop_box[1] * h),
                         int(crop_box[2] * w), int(crop_box[3] * h)))
        cw, ch = crop.size
        got = [{"region": (
            crop_box[0] + r["region"][0] * cw / w,
            crop_box[1] + r["region"][1] * ch / h,
            crop_box[0] + r["region"][2] * cw / w,
            crop_box[1] + r["region"][3] * ch / h), "conf": r["conf"]}
               for r in yolo.detect_boxes(crop)]
        refined.append({"coco_region": region, "yolo": got})
    return {"coco": [{"region": b["region"], "conf": b["conf"], "cls": b["cls"]} for b in coco],
            "refine": refined}
