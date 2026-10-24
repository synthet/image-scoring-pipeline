"""Blind multi-CLI culling panel for the human culling label set (#415).

Vision judges grade every frame of a ``human_labels`` sample group (2 pick / 1 keep / 0 reject) and
mark one best frame, with the same semantics as the owner labelling tool
(``docs/planning/human-culling-labels.md``). Their consensus is an **agent-panel label**, not an
owner label. Split frames go to Jev on sanitized text, outside this script (Jev is text-only).

Layout under ``--root`` (git-ignored scratch; ``key.json`` maps tokens to private photos):

    groups/<gtoken>/<gtoken>_F<n>.jpg / _F<n>_crop.jpg   blind frames, one folder per group
    groups.json            gtoken, frame count, pilot flag (judges never see it)
    key.json               gtoken -> unit_id and frame ids -> image_id (stays local)
    judges/<judge>/<gtoken>.txt   raw CLI replies

Steps:

    # container (needs modules + DB)
    python scripts/research/judges/culling_panel.py build --root <root>
    # host
    python scripts/research/judges/culling_panel.py run --judge claude --root <root> [--pilot]
    python scripts/research/judges/culling_panel.py consensus --root <root> --judges claude,codex,agy,cursor
    # container
    python scripts/research/judges/culling_panel.py calibrate --root <root> --judges claude,codex,agy,cursor
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.research.judges.species_panel import _call, command, wilson  # noqa: E402

FULL_SIDE = 1280
CROP_SIDE = 1280
BOX_PAD = 0.25
PILOT_GROUPS = 20
OWNER = "V"
NONE = "none"


# ---------------------------------------------------------------------------
# build (container)
# ---------------------------------------------------------------------------

def crop_region(boxes: Sequence[Sequence[float]], width: int, height: int) -> tuple[int, int, int, int]:
    """One near-native detail window for the whole group, like the owner tool's 100 % loupe.

    ``boxes`` are display-normalized ``(x1, y1, x2, y2)`` subject regions of the group's frames. The
    square window is centred on their union (the frame centre without boxes); its side is the union's
    longer side plus ``BOX_PAD``, kept between ``CROP_SIDE`` and ``2 * CROP_SIDE`` native pixels so
    the crop is shown at 100-50 % scale.
    """
    if boxes:
        x1, y1 = min(b[0] for b in boxes) * width, min(b[1] for b in boxes) * height
        x2, y2 = max(b[2] for b in boxes) * width, max(b[3] for b in boxes) * height
        cx, cy, span = (x1 + x2) / 2, (y1 + y2) / 2, max(x2 - x1, y2 - y1) * (1 + 2 * BOX_PAD)
    else:
        cx, cy, span = width / 2, height / 2, 0
    side = min(max(span, CROP_SIDE), 2 * CROP_SIDE, width, height)
    left = min(max(0, cx - side / 2), width - side)
    top = min(max(0, cy - side / 2), height - side)
    return (int(left), int(top), int(left + side), int(top + side))


def _fit(img, side: int):
    img = img.copy()
    img.thumbnail((side, side))
    return img


def build(root: Path, limit: int | None) -> dict:
    from modules import db
    from modules.thumbnails import bake_orientation, extract_embedded_jpeg
    from PIL import Image

    conn = db.get_connector()
    units = conn.query(
        "SELECT u.unit_id, u.sample_order, u.image_ids, "
        "EXISTS (SELECT 1 FROM human_labels.unit_status s WHERE s.unit_id = u.unit_id AND s.labeler = ?) AS owner_done "
        "FROM human_labels.units u WHERE u.sample_version = 'v1' ORDER BY u.sample_order", (OWNER,))
    pilot_ids = {u["unit_id"] for u in units if u["owner_done"]}
    pilot_ids = set(sorted(pilot_ids, key=lambda i: next(u["sample_order"] for u in units if u["unit_id"] == i))[:PILOT_GROUPS])
    key = json.loads((root / "key.json").read_text(encoding="utf-8")) if (root / "key.json").exists() else {}
    done_units = {v["unit_id"] for v in key.values()}
    groups = json.loads((root / "groups.json").read_text(encoding="utf-8")) if (root / "groups.json").exists() else []
    stats: Counter = Counter()
    for u in units[:limit]:
        if u["unit_id"] in done_units:
            continue
        rows = conn.query(
            "SELECT i.id, i.file_path, e.date_time_original, e.sub_sec_time_original, "
            "(SELECT ARRAY[rg.x1, rg.y1, rg.x2, rg.y2] FROM image_localization_runs lr "
            " JOIN image_regions rg ON rg.localization_run_id = lr.id "
            " WHERE lr.image_id = i.id AND lr.is_current AND lr.coord_space = 'display_normalized' AND rg.rank = 0 "
            " ORDER BY rg.confidence DESC NULLS LAST LIMIT 1) AS region "
            "FROM images i LEFT JOIN image_exif e ON e.image_id = i.id WHERE i.id = ANY(?)", (list(u["image_ids"]),))
        rows.sort(key=lambda r: (str(r["date_time_original"] or ""), str(r["sub_sec_time_original"] or ""), r["file_path"]))
        decoded = []
        for r in rows:
            img = None
            if Path(r["file_path"]).suffix.lower() in {".jpg", ".jpeg"}:
                try:
                    img = Image.open(r["file_path"])
                    img.load()
                except OSError:
                    img = None
            else:
                img = extract_embedded_jpeg(r["file_path"])
            if img is None:
                stats["frame_decode_failed"] += 1
                continue
            decoded.append((r, bake_orientation(img, r["file_path"]).convert("RGB")))
        if len(decoded) < 2:
            stats["group_skipped_too_few_frames"] += 1
            continue
        gtoken = secrets.token_hex(6)
        gdir = root / "groups" / gtoken
        gdir.mkdir(parents=True, exist_ok=True)
        w, h = decoded[0][1].size
        boxes = [tuple(float(v) for v in r["region"]) for r, _ in decoded if r["region"]]
        region = crop_region(boxes, w, h)
        frames = {}
        for n, (r, img) in enumerate(decoded, start=1):
            fid = f"F{n}"
            _fit(img, FULL_SIDE).save(gdir / f"{gtoken}_{fid}.jpg", quality=90)
            reg = region if img.size == (w, h) else crop_region(boxes, *img.size)
            _fit(img.crop(reg), CROP_SIDE).save(gdir / f"{gtoken}_{fid}_crop.jpg", quality=92)
            frames[fid] = r["id"]
        key[gtoken] = {"unit_id": u["unit_id"], "frames": frames}
        groups.append({"gtoken": gtoken, "n": len(frames), "pilot": u["unit_id"] in pilot_ids})
        stats["groups"] += 1
        stats["frames"] += len(frames)
        (root / "key.json").write_text(json.dumps(key), encoding="utf-8")
        (root / "groups.json").write_text(json.dumps(groups), encoding="utf-8")
        print(f"built {stats['groups']} groups {dict(stats)}", flush=True)
    return dict(stats)


# ---------------------------------------------------------------------------
# judges (host)
# ---------------------------------------------------------------------------

def prompt_for(group: dict, judge: str, gdir: Path) -> str:
    how = {"codex": "The photos are attached as images, two per frame in the order listed below."}.get(
        judge, "Open each local JPEG at the paths below to look at it. Do not modify files or run programs.")
    g = group["gtoken"]
    items = "\n".join(f"- {f}: full frame {(gdir / f'{g}_{f}.jpg').resolve()} ; "
                      f"detail crop {(gdir / f'{g}_{f}_crop.jpg').resolve()}"
                      for f in (f"F{n}" for n in range(1, group["n"] + 1)))
    return (
        f"Independent photo culling for a photographer's label set. {how}\n{items}\n\n"
        f"These {group['n']} frames were shot within moments of each other, listed in capture order. "
        "Each frame has a full view and a detail crop of the same region in every frame, at full "
        "resolution, so you can compare sharpness (especially eyes), motion blur, pose, expression and "
        "framing between frames.\n\n"
        "Grade every frame as the photographer would when culling:\n"
        "- 2 = pick: would keep and use.\n"
        "- 1 = keep: acceptable, not a first choice.\n"
        "- 0 = reject: would delete.\n"
        "Mark exactly one best frame (the one to keep if only one could stay). The best frame must be "
        "graded 2. Only when every frame is graded 0 may there be no best frame.\n"
        "If the frames are not one moment or are identical copies, set skip to true and say why.\n"
        "Give each frame a reason of at most 15 words.\n\n"
        'Return only JSON: {"skip":false,"skip_reason":"","frames":[{"id":"F1","grade":2,"best":true,'
        '"reason":"..."}]} with every frame listed above.')


def parse_reply(text: str, n: int) -> dict | None:
    """A validated reply, or ``None`` when it breaks the rubric."""
    match = None
    for m in re.finditer(r"\{.*\}", text, re.S):
        match = m
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if data.get("skip"):
        return {"skip": True, "skip_reason": str(data.get("skip_reason") or "")[:200], "frames": {}}
    ids = {f"F{i}" for i in range(1, n + 1)}
    frames = {}
    for f in data.get("frames") or []:
        fid, grade = str(f.get("id")), f.get("grade")
        if fid not in ids or grade not in (0, 1, 2):
            return None
        frames[fid] = {"grade": grade, "best": bool(f.get("best")), "reason": str(f.get("reason") or "")[:160]}
    if set(frames) != ids:
        return None
    best = [fid for fid, f in frames.items() if f["best"]]
    if len(best) > 1 or (best and frames[best[0]]["grade"] != 2):
        return None
    if not best and any(f["grade"] for f in frames.values()):
        return None
    return {"skip": False, "skip_reason": "", "frames": frames, "best": best[0] if best else NONE}


def load_groups(root: Path) -> list[dict]:
    return json.loads((root / "groups.json").read_text(encoding="utf-8"))


def load_judge(root: Path, judge: str) -> dict[str, dict]:
    sizes = {g["gtoken"]: g["n"] for g in load_groups(root)}
    out = {}
    for p in (root / "judges" / judge).glob("*.txt"):
        if p.stem in sizes:
            reply = parse_reply(p.read_text(encoding="utf-8", errors="replace"), sizes[p.stem])
            if reply:
                out[p.stem] = reply
    return out


def run(root: Path, judge: str, timeout: int, pilot: bool, limit: int | None) -> Counter:
    done = load_judge(root, judge)
    todo = [g for g in load_groups(root) if g["pilot"] == pilot and g["gtoken"] not in done][:limit]
    out_dir = root / "judges" / judge
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    fails = 0
    for i, g in enumerate(todo, start=1):
        gdir = root / "groups" / g["gtoken"]
        out = out_dir / f"{g['gtoken']}.txt"
        paths = [gdir / f"{g['gtoken']}_F{n}{s}.jpg" for n in range(1, g["n"] + 1) for s in ("", "_crop")]
        ok = False
        for _attempt in range(2):
            out.unlink(missing_ok=True)
            argv, stdin, cwd = command(judge, prompt_for(g, judge, gdir), paths, out, gdir)
            try:
                stdout, stderr = _call(argv, stdin, cwd, timeout)
            except subprocess.TimeoutExpired:
                counts["timeout"] += 1
                continue
            if judge != "codex" or not out.exists():
                out.write_text(stdout, encoding="utf-8")
            (out_dir / f"{g['gtoken']}.stderr.log").write_text(stderr[-4000:], encoding="utf-8")
            if parse_reply(out.read_text(encoding="utf-8", errors="replace"), g["n"]):
                ok = True
                break
            counts["invalid_reply"] += 1
        counts["labelled" if ok else "failed"] += 1
        fails = 0 if ok else fails + 1
        print(f"{judge}: {i}/{len(todo)} {dict(counts)}", flush=True)
        if fails >= 3:
            counts["stopped_after_3_failures"] = 1
            break
    return counts


# ---------------------------------------------------------------------------
# consensus (host)
# ---------------------------------------------------------------------------

def group_consensus(n: int, replies: list[dict | None], need: int) -> dict:
    """Per-frame consensus grades and best frame; ``None`` marks a split."""
    valid = [r for r in replies if r and not r["skip"]]
    grades, splits = {}, []
    for fid in (f"F{i}" for i in range(1, n + 1)):
        top = Counter(r["frames"][fid]["grade"] for r in valid).most_common(1)
        grades[fid] = top[0][0] if top and top[0][1] >= need else None
        if grades[fid] is None:
            splits.append(fid)
    top = Counter(r["best"] for r in valid).most_common(1)
    best = top[0][0] if top and top[0][1] >= need else None
    skips = sum(1 for r in replies if r and r["skip"])
    return {"grades": grades, "best": best, "grade_splits": splits, "skip_votes": skips}


def consensus(root: Path, judges: list[str]) -> dict:
    groups = load_groups(root)
    votes = {j: load_judge(root, j) for j in judges}
    need = 3 if len(judges) >= 4 else 2
    result, splits = {}, []
    for g in groups:
        replies = [votes[j].get(g["gtoken"]) for j in judges]
        c = group_consensus(g["n"], replies, need)
        c["replies"] = sum(1 for r in replies if r)
        result[g["gtoken"]] = c
        if c["best"] is None or c["grade_splits"]:
            splits.append({
                "gtoken": g["gtoken"],
                "best_split": c["best"] is None,
                "grade_splits": c["grade_splits"],
                "votes": {j: votes[j][g["gtoken"]] for j in judges if g["gtoken"] in votes[j]},
            })
    (root / "consensus.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (root / "splits.json").write_text(json.dumps(splits, indent=1), encoding="utf-8")
    return {"groups": len(groups), "best_resolved": sum(1 for c in result.values() if c["best"] is not None),
            "frames": sum(len(c["grades"]) for c in result.values()),
            "frames_resolved": sum(1 for c in result.values() for v in c["grades"].values() if v is not None),
            "groups_with_splits": len(splits)}


# ---------------------------------------------------------------------------
# calibration against the owner (container)
# ---------------------------------------------------------------------------

def weighted_kappa(pairs: list[tuple[int, int]], k: int = 3) -> float | None:
    """Quadratic-weighted Cohen's kappa for ordinal grades 0..k-1."""
    if not pairs:
        return None
    n = len(pairs)
    obs = [[0.0] * k for _ in range(k)]
    for a, b in pairs:
        obs[a][b] += 1
    ra = [sum(obs[i]) for i in range(k)]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * obs[i][j]
            den += w * ra[i] * rb[j] / n
    return 1.0 - num / den if den else None


def compare(owner: dict, panel: dict) -> dict:
    """Agreement of one labeller (``panel``) with the owner over groups both labelled.

    Both map ``unit_id -> {"grades": {image_id: grade|None}, "best": image_id|"none"|None}``.
    """
    best_k = best_n = 0
    grade_pairs, pair_agree, pair_n, pair_tie = [], 0, 0, 0
    for uid, o in owner.items():
        p = panel.get(uid)
        if not p:
            continue
        if p["best"] is not None:
            best_n += 1
            best_k += p["best"] == o["best"]
        common = [i for i in o["grades"] if p["grades"].get(i) is not None]
        grade_pairs += [(o["grades"][i], p["grades"][i]) for i in common]
        for x in range(len(common)):
            for y in range(x + 1, len(common)):
                a, b = common[x], common[y]
                if o["grades"][a] == o["grades"][b]:
                    continue
                pair_n += 1
                d = (o["grades"][a] - o["grades"][b]) * (p["grades"][a] - p["grades"][b])
                pair_agree += d > 0
                pair_tie += d == 0
    lo, hi = wilson(best_k, best_n)
    return {
        "best_agree": best_k, "best_n": best_n, "best_rate": round(best_k / best_n, 3) if best_n else None,
        "best_ci95": [round(lo, 3), round(hi, 3)],
        "frames": len(grade_pairs),
        "grade_exact": round(sum(a == b for a, b in grade_pairs) / len(grade_pairs), 3) if grade_pairs else None,
        "kappa_quadratic": round(weighted_kappa(grade_pairs), 3) if grade_pairs else None,
        "pairs": pair_n, "pair_order_agree": round(pair_agree / pair_n, 3) if pair_n else None,
        "pair_ties": pair_tie,
    }


def _to_units(root: Path, by_gtoken: dict) -> dict:
    """Panel/judge results keyed by token -> owner keying (unit_id, image ids)."""
    key = json.loads((root / "key.json").read_text(encoding="utf-8"))
    out = {}
    for g, c in by_gtoken.items():
        frames = key[g]["frames"]
        best = c["best"]
        out[key[g]["unit_id"]] = {
            "grades": {frames[f]: v for f, v in c["grades"].items()},
            "best": NONE if best == NONE else (frames[best] if best else None),
        }
    return out


def calibrate(root: Path, judges: list[str], jev: Path | None) -> dict:
    from modules import db

    conn = db.get_connector()
    owner: dict = {}
    for r in conn.query("SELECT unit_id, image_id, grade, is_best FROM human_labels.labels WHERE labeler = ?", (OWNER,)):
        o = owner.setdefault(r["unit_id"], {"grades": {}, "best": NONE})
        o["grades"][r["image_id"]] = r["grade"]
        if r["is_best"]:
            o["best"] = r["image_id"]
    cons = json.loads((root / "consensus.json").read_text(encoding="utf-8"))
    if jev and jev.exists():
        for item in json.loads(jev.read_text(encoding="utf-8")):
            c = cons[item["gtoken"]]
            if item["kind"] == "best":
                c["best"] = item["answer"]
            else:
                c["grades"][item["frame"]] = item["answer"]
    report = {"panel": compare(owner, _to_units(root, cons))}
    for j in judges:
        report[j] = compare(owner, _to_units(root, {
            g: {"grades": {f: v["grade"] for f, v in r["frames"].items()}, "best": r["best"]}
            for g, r in load_judge(root, j).items() if not r["skip"]}))
    # context: score_general's top frame as a "labeller" for the best frame only
    units = {r["unit_id"]: r["image_ids"] for r in conn.query("SELECT unit_id, image_ids FROM human_labels.units")}
    scores = {r["id"]: r["score_general"] for r in conn.query(
        "SELECT id, score_general FROM images WHERE id = ANY(?)", ([i for v in units.values() for i in v],))}
    baseline = {}
    for uid in owner:
        scored = [(scores.get(i), i) for i in units[uid] if scores.get(i) is not None]
        if scored:
            baseline[uid] = {"grades": {}, "best": max(scored)[1]}
    report["score_general_top1"] = compare(owner, baseline)
    report["coverage"] = {
        "groups": len(cons),
        "best_resolved": sum(1 for c in cons.values() if c["best"] is not None),
        "frames": sum(len(c["grades"]) for c in cons.values()),
        "frames_resolved": sum(1 for c in cons.values() for v in c["grades"].values() if v is not None),
        "owner_groups": len(owner),
    }
    (root / "calibration.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--root", type=Path, required=True)
    b.add_argument("--limit", type=int)
    r = sub.add_parser("run")
    r.add_argument("--root", type=Path, required=True)
    r.add_argument("--judge", required=True)
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--pilot", action="store_true")
    r.add_argument("--limit", type=int)
    c = sub.add_parser("consensus")
    c.add_argument("--root", type=Path, required=True)
    c.add_argument("--judges", required=True)
    k = sub.add_parser("calibrate")
    k.add_argument("--root", type=Path, required=True)
    k.add_argument("--judges", required=True)
    k.add_argument("--jev", type=Path)
    a = ap.parse_args()
    if a.cmd == "build":
        print(json.dumps(build(a.root, a.limit)))
    elif a.cmd == "run":
        print(json.dumps(run(a.root, a.judge, a.timeout, a.pilot, a.limit)))
    elif a.cmd == "consensus":
        print(json.dumps(consensus(a.root, a.judges.split(","))))
    else:
        print(json.dumps(calibrate(a.root, a.judges.split(","), a.jev), indent=1))


if __name__ == "__main__":
    main()
