"""Blind multi-CLI species panel for the Stage 5 promotion gate (#592).

Vision judges (Claude Code, Codex, Antigravity, Cursor agent, Gemini CLIs) name the bird in each
blind crop and choose between two candidate names shown as A/B in random order. Their consensus is
an **agent-panel label**, not an owner label. Split frames go to Jev on species-blind text, outside
this script (Jev is text-only).

Layout under ``--root`` (git-ignored scratch; the manifest maps tokens to private photos):

    blind/<token>.jpg      crops with random names, no EXIF, nothing else in the folder
    manifest.json          token -> image_id, stratum, A/B names, region hint (stays local)
    judges/<judge>/*.txt   raw CLI replies

Steps:

    # container (needs modules + DB): sample the frozen comparison and cut the crops
    python scripts/research/judges/species_panel.py build --full <full.json> --root <root>
    # host: label control frames to vet each judge, then the sample
    python scripts/research/judges/species_panel.py pilot --panel-dir <dir> --panel-json <json> --root <pilot>
    python scripts/research/judges/species_panel.py run --judge claude --root <root>
    python scripts/research/judges/species_panel.py consensus --root <root> --judges claude,codex,agy,cursor
    python scripts/research/judges/species_panel.py gate --root <root> --full <full.json>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import secrets
import shutil
import subprocess
from collections import Counter
from pathlib import Path

#: Sample sizes per outcome stratum of the frozen comparison (pre-registered in the run contract).
STRATA = {"changed": 150, "same": 100, "now_labelled": 60, "now_abstains": 60, "both_abstain": 20}
CHOICES = ("A", "B", "NEITHER", "UNSURE")
CROP_PAD = 0.35
CROP_SIDE = 768
OTHER = "__other__"  # both candidates wrong, judges disagree on what it is


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval; same formula as ``detector_benchmark/v1_promotion_gate.py``."""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def norm(name: str | None) -> str | None:
    """Comparable species key: case, spacing, hyphens and apostrophes do not matter."""
    if not name:
        return None
    key = re.sub(r"[^a-z]", "", name.lower().replace("grey", "gray"))
    return key or None


def candidates(row: dict) -> list[str]:
    """The two names a frame is judged between: stored label, new top-1, then the next ranks."""
    names = [row.get("old"), row.get("new_top")] + [n for n, _ in (row.get("new_top3") or [])]
    out: list[str] = []
    for n in names:
        if n and norm(n) not in {norm(o) for o in out}:
            out.append(n)
    return out[:2]


def region_hint(lat: float | None, lon: float | None) -> str:
    """Coarse location (1 degree) so judges can apply a range prior; no exact coordinates."""
    if lat is None or lon is None:
        return "location unknown (collection is mostly from the southern USA)"
    return f"photographed near latitude {round(lat)}, longitude {round(lon)}"


def sample(images: list[dict], seed: int, strata: dict[str, int] | None = None) -> list[dict]:
    rng = random.Random(seed)
    picked = []
    for stratum, n in (strata or STRATA).items():
        rows = sorted((r for r in images if r["outcome"] == stratum), key=lambda r: r["image_id"])
        picked += [dict(r, stratum=stratum, stratum_size=len(rows)) for r in rng.sample(rows, min(n, len(rows)))]
    return picked


# ---------------------------------------------------------------------------
# build (container)
# ---------------------------------------------------------------------------

_SELECTION_SQL = """
    SELECT s.image_id, g.x1, g.y1, g.x2, g.y2, i.file_path, e.gps_latitude, e.gps_longitude
    FROM image_localization_selections s
    JOIN image_regions g ON g.id = s.region_id
    JOIN images i ON i.id = s.image_id
    LEFT JOIN image_exif e ON e.image_id = s.image_id
    WHERE s.revoked_at IS NULL AND s.detector_key = 'bird'
"""


def padded_crop(img, region, pad: float = CROP_PAD, side: int = CROP_SIDE):
    w, h = img.size
    x1, y1, x2, y2 = region[0] * w, region[1] * h, region[2] * w, region[3] * h
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    box = (max(0, int(x1 - px)), max(0, int(y1 - py)), min(w, int(math.ceil(x2 + px))), min(h, int(math.ceil(y2 + py))))
    crop = img.crop(box).convert("RGB")
    crop.thumbnail((side, side))
    return crop


def build(full: Path, root: Path, seed: int, strata: dict[str, int] | None = None) -> dict:
    """Sample and cut crops. Rows carrying ``region`` (e.g. boxes not yet selected) override the selection's."""
    import tempfile

    from modules import db
    from modules.thumbnails import open_oriented_for_ml

    data = json.loads(full.read_text(encoding="utf-8"))
    picked = sample(data["images"], seed, strata)
    rows = {int(r["image_id"]): r for r in db.get_connector().query(_SELECTION_SQL, ())}
    blind = root / "blind"
    blind.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed + 1)
    manifest = []
    with tempfile.TemporaryDirectory(prefix="species-panel-") as tmp:
        for n, row in enumerate(picked, 1):
            sel = rows.get(int(row["image_id"])) or {}
            if row.get("region"):
                img_row = db.get_connector().query_one(
                    "SELECT i.file_path, e.gps_latitude, e.gps_longitude FROM images i "
                    "LEFT JOIN image_exif e ON e.image_id = i.id WHERE i.id = ?", (int(row["image_id"]),))
                sel = dict(img_row, **dict(zip(("x1", "y1", "x2", "y2"), row["region"])))
            src = Path(sel["file_path"])
            staged = Path(tmp) / ("image" + src.suffix.lower())
            shutil.copyfile(src, staged)  # local bytes: avoids the 9p ExifTool timeouts
            assert staged.stat().st_size == src.stat().st_size
            img = open_oriented_for_ml(str(staged))
            crop = padded_crop(img, tuple(float(sel[k]) for k in ("x1", "y1", "x2", "y2")))
            token = secrets.token_hex(6)
            crop.save(blind / f"{token}.jpg", "JPEG", quality=92)
            staged.unlink()
            names = candidates(row)
            if len(names) < 2:
                raise ValueError(f"image {row['image_id']} has fewer than two candidate names")
            if rng.random() < 0.5:
                names.reverse()
            manifest.append({"token": token, "image_id": int(row["image_id"]), "stratum": row["stratum"],
                             "stratum_size": row["stratum_size"], "A": names[0], "B": names[1],
                             "hint": region_hint(sel["gps_latitude"], sel["gps_longitude"])})
            if n % 25 == 0:
                print(f"build: {n}/{len(picked)}", flush=True)
    rng.shuffle(manifest)
    (root / "manifest.json").write_text(json.dumps({"seed": seed, "source": str(full), "frames": manifest}, indent=1),
                                        encoding="utf-8")
    return {"frames": len(manifest), "by_stratum": dict(Counter(m["stratum"] for m in manifest))}


def pilot(panel_dir: Path, panel_json: Path, species_list: Path, root: Path, seed: int) -> dict:
    """Control frames from the 2026-09-24 panel where both models agreed; decoy = a random list name."""
    rows = [r for r in json.loads(panel_json.read_text(encoding="utf-8")) if r["agree"]]
    names = [ln.strip() for ln in species_list.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    rng = random.Random(seed)
    blind = root / "blind"
    blind.mkdir(parents=True, exist_ok=False)
    manifest = []
    for r in rows:
        token = secrets.token_hex(6)
        shutil.copyfile(panel_dir / f"img_{r['image_id']}.jpg", blind / f"{token}.jpg")
        decoy = rng.choice([n for n in names if norm(n) != norm(r["prod"])])
        pair = [r["prod"], decoy] if rng.random() < 0.5 else [decoy, r["prod"]]
        manifest.append({"token": token, "image_id": int(r["image_id"]), "stratum": "control", "truth": r["prod"],
                         "A": pair[0], "B": pair[1], "hint": region_hint(None, None)})
    rng.shuffle(manifest)
    (root / "manifest.json").write_text(json.dumps({"seed": seed, "frames": manifest}, indent=1), encoding="utf-8")
    return {"frames": len(manifest)}


# ---------------------------------------------------------------------------
# run (host)
# ---------------------------------------------------------------------------

JUDGES = ("claude", "codex", "agy", "cursor", "gemini")


def prompt_for(frames: list[dict], judge: str, blind: Path) -> str:
    how = {"codex": "The photos are attached as images, in the order listed.",
           "gemini": "Each photo is referenced with @ below.",
           }.get(judge, "Open each local JPEG at the path below to look at it. Do not modify files or run programs.")
    items = []
    for f in frames:
        path = blind / f"{f['token']}.jpg"
        ref = f"@{path.name}" if judge == "gemini" else str(path.resolve())
        items.append(f"- id {f['token']}: {ref} ({f['hint']}). A) {f['A']}  B) {f['B']}")
    return ("You are an expert field ornithologist labelling bird photos. " + how + "\n" + "\n".join(items) + "\n\n"
            "Answer only from the photos; do not browse other files. For each photo: first identify the main bird yourself (common North American English name; use "
            "the location to rule out out-of-range look-alikes). Then choose A or B if one of the two names is "
            "correct, NEITHER if both are wrong, UNSURE if the photo cannot decide (no bird visible, too blurred).\n"
            'Return only JSON, no table or prose: {"images":[{"id":"<id>","own_id":"<species>",'
            '"choice":"A|B|NEITHER|UNSURE"}]} with every id listed above.')


def command(judge: str, prompt: str, paths: list[Path], out: Path, blind: Path) -> tuple[list[str], str | None, Path]:
    """(argv, stdin text, cwd) for one judge call."""
    if judge == "codex":
        cli = Path(os.environ["APPDATA"]) / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        args = ["node", str(cli), "exec", "--sandbox", "read-only", "--cd", str(blind.resolve()), "--skip-git-repo-check",
                "--ephemeral", "--output-last-message", str(out.resolve())]
        for p in paths:
            args += ["--image", str(p.resolve())]
        return [*args, "-"], prompt, blind
    if judge == "agy":
        return ([str(Path(os.environ["LOCALAPPDATA"]) / "agy" / "bin" / "agy.exe"), "-p", prompt, "--mode", "plan",
                 "--add-dir", str(blind.resolve()), "--dangerously-skip-permissions", "--output-format", "text"],
                None, blind)
    if judge == "cursor":
        # node + index.js directly: the .cmd/.ps1 shims cut a multi-line prompt at its first newline.
        ver = max((d for d in (Path(os.environ["LOCALAPPDATA"]) / "cursor-agent" / "versions").iterdir()
                   if re.match(r"\d{4}\.\d{2}\.\d{2}-", d.name)), key=lambda d: d.name)
        os.environ.setdefault("CURSOR_INVOKED_AS", "cursor-agent")
        return ([str(ver / "node.exe"), str(ver / "index.js"), "-p", "--mode", "ask", "--trust",
                 "--output-format", "text", prompt], None, blind)
    if judge == "gemini":
        return ([shutil.which("gemini") or "gemini", "--approval-mode", "plan", "-o", "text", "-p",
                 "Answer the request above."], prompt, blind)
    return ([str(Path(os.environ["USERPROFILE"]) / ".local" / "bin" / "claude.exe"), "-p", prompt, "--tools", "Read",
             "--add-dir", str(blind.resolve()), "--output-format", "text"], None, blind)


def parse_reply(text: str) -> dict[str, dict]:
    """Last JSON object with an ``images`` list -> {token: {own_id, choice}}."""
    decoder = json.JSONDecoder()
    for start in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            data, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("images"), list):
            out = {}
            for row in data["images"]:
                choice = str(row.get("choice", "")).strip().upper()
                if row.get("id") and choice in CHOICES:
                    out[str(row["id"])] = {"own_id": str(row.get("own_id") or ""), "choice": choice}
            return out
    return {}


def load_frames(root: Path) -> list[dict]:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))["frames"]


def load_judge(root: Path, judge: str) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for f in sorted((root / "judges" / judge).glob("*.txt")):
        labels.update(parse_reply(f.read_text(encoding="utf-8", errors="replace")))
    return labels


def _call(argv: list[str], stdin: str | None, cwd: Path, timeout: int) -> tuple[str, str]:
    """Run one CLI call; on timeout kill the whole process tree (``.cmd`` shims keep pipes open)."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", cwd=cwd)
    try:
        return proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.kill()
        proc.communicate()
        raise


def stage_batch(blind: Path, names: list[str], dest: Path) -> Path:
    """Copy one batch into its own folder: the Cursor agent otherwise reads the whole working folder."""
    dest.mkdir(parents=True, exist_ok=True)
    for n in names:
        if not (dest / n).exists():
            shutil.copyfile(blind / n, dest / n)
    return dest


def run(root: Path, judge: str, batch_size: int, timeout: int, limit: int | None, shard: str = "0/1") -> Counter:
    blind = root / "blind"
    done = load_judge(root, judge)
    k, n = (int(x) for x in shard.split("/"))
    frames = [f for i, f in enumerate(load_frames(root)) if i % n == k]
    todo = [f for f in frames if f["token"] not in done][:limit]
    out_dir = root / "judges" / judge
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    fails = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        out = out_dir / f"{batch[0]['token']}.txt"
        where = stage_batch(blind, [f"{f['token']}.jpg" for f in batch], root / "staged" / batch[0]["token"])             if judge == "cursor" else blind
        paths = [where / f"{f['token']}.jpg" for f in batch]
        argv, stdin, cwd = command(judge, prompt_for(batch, judge, where), paths, out, where)
        try:
            stdout, stderr = _call(argv, stdin, cwd, timeout)
            if judge != "codex" or not out.exists():
                out.write_text(stdout, encoding="utf-8")
            (out_dir / f"{out.stem}.stderr.log").write_text(stderr[-4000:], encoding="utf-8")
        except subprocess.TimeoutExpired:
            counts["timeout"] += len(batch)
            fails += 1
        else:
            got = parse_reply(out.read_text(encoding="utf-8", errors="replace"))
            ok = len(set(got) & {f["token"] for f in batch})
            counts["labelled"] += ok
            counts["missing"] += len(batch) - ok
            fails = 0 if ok else fails + 1
        print(f"{judge}: {start + len(batch)}/{len(todo)} {dict(counts)}", flush=True)
        if fails >= 3:
            counts["stopped_after_3_failures"] = 1
            break
    return counts


# ---------------------------------------------------------------------------
# consensus and gate
# ---------------------------------------------------------------------------

def vote(frame: dict, answer: dict | None) -> str | None:
    """A judge's species for a frame: the chosen candidate, its own ID on NEITHER, ``None`` when unsure."""
    if not answer:
        return None
    if answer["choice"] in ("A", "B"):
        return norm(frame[answer["choice"]])
    if answer["choice"] == "NEITHER":
        own = norm(answer["own_id"])
        return own if own and own not in (norm(frame["A"]), norm(frame["B"])) else OTHER
    return None


def consensus_label(frame: dict, answers: list[dict | None], need: int) -> str | None:
    """Species key with at least ``need`` votes; ``OTHER`` when that many judges reject both names."""
    votes = [vote(frame, a) for a in answers]
    counts = Counter(v for v in votes if v)
    if counts:
        top, n = counts.most_common(1)[0]
        if n >= need:
            return top
    rejected = sum(1 for v in votes if v and v not in (norm(frame["A"]), norm(frame["B"])))
    return OTHER if rejected >= need else None


def consensus(root: Path, judges: list[str]) -> dict:
    frames = load_frames(root)
    votes = {j: load_judge(root, j) for j in judges}
    need = 2 if len(judges) == 3 else 3
    labels, splits = {}, []
    for f in frames:
        answers = [votes[j].get(f["token"]) for j in judges]
        label = consensus_label(f, answers, need)
        labels[f["token"]] = label
        if label is None:
            splits.append({"token": f["token"], "A": f["A"], "B": f["B"],
                           "votes": {j: votes[j].get(f["token"]) for j in judges}})
    pairwise = {}
    for i, a in enumerate(judges):
        for b in judges[i + 1:]:
            both = [f for f in frames if f["token"] in votes[a] and f["token"] in votes[b]]
            pairwise[f"{a}~{b}"] = [sum(vote(f, votes[a][f["token"]]) == vote(f, votes[b][f["token"]]) for f in both),
                                    len(both)]
    summary = {"judges": judges, "need": need, "frames": len(frames),
               "coverage": {j: len(set(votes[j]) & {f["token"] for f in frames}) for j in judges},
               "labelled": sum(1 for v in labels.values() if v), "splits": len(splits), "pairwise": pairwise}
    if any("truth" in f for f in frames):
        summary["control_correct"] = {
            j: sum(1 for f in frames if vote(f, votes[j].get(f["token"])) == norm(f["truth"])) for j in judges}
    (root / "consensus.json").write_text(json.dumps({"summary": summary, "labels": labels}, indent=1), encoding="utf-8")
    (root / "splits.json").write_text(json.dumps(splits, indent=1), encoding="utf-8")
    return summary


def leaks(text: str, names: list[str]) -> list[str]:
    """Species or group words (last word of any list name, e.g. "wren") present in ``text``."""
    words = set(re.findall(r"[a-z]+", text.lower().replace("-", " ")))
    groups = {n.lower().replace("-", " ").split()[-1] for n in names}
    hits = sorted(groups & words)
    hits += [n for n in names if n.lower() in text.lower() and n.lower().split()[-1] not in hits]
    return hits


def describe(root: Path, species_list: Path, timeout: int) -> dict:
    """Species-blind field-mark descriptions of split frames (Claude CLI), for Jev on text."""
    names = [ln.strip() for ln in species_list.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    frames = {f["token"]: f for f in load_frames(root)}
    splits = json.loads((root / "splits.json").read_text(encoding="utf-8"))
    out_path = root / "described.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    blind = root / "blind"
    for s in splits:
        if s["token"] in done:
            continue
        f = frames[s["token"]]
        prompt = (f"Open the local JPEG {(blind / (f['token'] + '.jpg')).resolve()} and describe the main bird's "
                  "visible field marks for an identification by someone else: size cues, bill shape and colour, "
                  "plumage colours and patterns by body part, leg colour, posture and habitat. Never name a species, "
                  "family or group (no words like hawk, heron, wren, sparrow, duck). If no bird is visible, say so. "
                  "At most 120 words, plain text.")
        argv, stdin, cwd = command("claude", prompt, [], blind / "x", blind)
        try:
            text, _ = _call(argv, stdin, cwd, timeout)
        except subprocess.TimeoutExpired:
            continue
        done[s["token"]] = {"text": text.strip(), "leaks": leaks(text, names + [f["A"], f["B"]])}
        out_path.write_text(json.dumps(done, indent=1), encoding="utf-8")
    return {"splits": len(splits), "described": len(done), "leaking": sum(1 for d in done.values() if d["leaks"])}


def gate(root: Path, full: Path, adjudicated: Path | None) -> dict:
    """Stage 5 criteria G5a-G5c from the consensus labels, weighted to the cohort by stratum."""
    frames = load_frames(root)
    labels = json.loads((root / "consensus.json").read_text(encoding="utf-8"))["labels"]
    if adjudicated and adjudicated.exists():
        labels.update({k: v for k, v in json.loads(adjudicated.read_text(encoding="utf-8")).items() if v})
    rows = {int(r["image_id"]): r for r in json.loads(full.read_text(encoding="utf-8"))["images"]}
    sizes = Counter(r["outcome"] for r in rows.values())
    per: dict[str, Counter] = {}
    for f in frames:
        c = per.setdefault(f["stratum"], Counter())
        truth = labels.get(f["token"])
        if truth is None:
            c["unresolved"] += 1
            continue
        row = rows[f["image_id"]]
        old, new = norm(row.get("old")), norm(row.get("new"))
        c["resolved"] += 1
        for side, name in (("old", old), ("new", new)):
            if name:
                c[f"{side}_labelled"] += 1
                c[f"{side}_right" if name == truth else f"{side}_wrong"] += 1
    weighted: dict[str, float] = {k: 0.0 for k in ("old_right", "old_wrong", "new_right", "new_wrong")}
    for stratum, c in per.items():
        w = sizes[stratum] / c["resolved"] if c["resolved"] else 0.0
        for k in ("old_right", "old_wrong", "new_right", "new_wrong"):
            weighted[k] += c[k] * w
    ch = per.get("changed", Counter())
    new_acc = weighted["new_right"] + weighted["new_wrong"]
    precision = weighted["new_right"] / new_acc if new_acc else 0.0
    n_eff = sum(c["new_labelled"] for c in per.values())
    lo, hi = wilson(precision * n_eff, n_eff)
    old_acc = weighted["old_right"] + weighted["old_wrong"]
    result = {
        "per_stratum": {s: dict(c) for s, c in per.items()},
        "weighted": {k: round(v, 1) for k, v in weighted.items()},
        "G5a": {"new_right": ch["new_right"], "old_right": ch["old_right"], "pass": ch["new_right"] >= ch["old_right"]},
        "G5b": {"pass": weighted["new_right"] >= weighted["old_right"] and weighted["new_wrong"] < weighted["old_wrong"]},
        "G5c": {"precision_new": round(precision, 4), "wilson95": [round(lo, 4), round(hi, 4)], "n_eff": n_eff,
                "pass": lo >= 0.85},
        "precision_old": round(weighted["old_right"] / old_acc, 4) if old_acc else None,
    }
    result["pass"] = all(result[g]["pass"] for g in ("G5a", "G5b", "G5c"))
    (root / "gate.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("action", choices=("build", "pilot", "run", "consensus", "describe", "gate"))
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--full", type=Path)
    p.add_argument("--seed", type=int, default=20261011)
    p.add_argument("--judge", choices=JUDGES)
    p.add_argument("--judges", default="claude,codex,agy,cursor")
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--limit", type=int)
    p.add_argument("--shard", default="0/1", help="k/n: this process judges frames i with i %% n == k")
    p.add_argument("--panel-dir", type=Path)
    p.add_argument("--panel-json", type=Path)
    p.add_argument("--species-list", type=Path, default=Path("data/bird_species_list.txt"))
    p.add_argument("--adjudicated", type=Path)
    p.add_argument("--strata", help='JSON sizes per outcome stratum, e.g. {"changed": 50}')
    a = p.parse_args()
    if a.action == "build":
        res = build(a.full, a.root, a.seed, json.loads(a.strata) if a.strata else None)
    elif a.action == "pilot":
        res = pilot(a.panel_dir, a.panel_json, a.species_list, a.root, a.seed)
    elif a.action == "run":
        if not a.judge:
            p.error("run needs --judge")
        res = run(a.root, a.judge, a.batch_size, a.timeout, a.limit, a.shard)
    elif a.action == "consensus":
        res = consensus(a.root, a.judges.split(","))
    elif a.action == "describe":
        res = describe(a.root, a.species_list, a.timeout)
    else:
        res = gate(a.root, a.full, a.adjudicated)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
