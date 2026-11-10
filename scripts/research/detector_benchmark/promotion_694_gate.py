"""Offline #694 receipts and gate analysis. No provider calls or database writes.

Run in gpu-shell: python -m scripts.research.detector_benchmark.promotion_694_gate
    verify | calibrate --panel <panel.json> --output <new.json>
    analyze --calibration <new.json> --manifest <blind-manifest.json>
            --panel <panel.json> [--adjudications <json>] --output <new.json>
    calibrate-r3 --panel <panel.json> --output <new.json>
    analyze-owner --record <owner-record.json> --output <new.json>
All outputs are local, create-only artifacts; frozen inputs are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

RULE_SHA256 = "541b17bed8f287482cb485cfb58fae3e144106c1e82b077fa3c5787e588d735a"
ANSWER_SHA256 = "fc1a5cab985cc566e23db2f69fe61309f4c6a4dadf180e56d3018136c24d7d3f"
FREEZE_SHA256 = "acc44121e591e24477a65e49f12e13cc63ac8836d1ddba2c4bfdf3d3bdafe170"
CALIBRATION_SHA256 = "11a64a57545afa6de38fe2976c4fbe9b8a67e158ce52e49e608dfb8dc121a73c"
AMENDMENT_SHA256 = "c3a466ea739580ec269ce802466e436c1101b3a1c1d093081e8569ae7511c763"
JUDGE_FREEZE_SHA256 = "7a3684661f1dfcb3c55db1fcc199b010396870b878cf0ff2bee6a23a4cf7fd0c"
# Rubric amendment, 2026-11-08 revision 2 (freeze-receipt-rubric-20261108.json).
R3_FREEZE_SHA256 = "16d6571ec17d52b794a5028556273365972cfeeeff4a7013a8222a6bbf1b87ce"
# Revision 3, 2026-11-09 (freeze-receipt-rubric-rev3-20261109.json).
REV3_FREEZE_SHA256 = "e6cbfdc05b3645956dfc46d2e57112eb7e20bd5e9a8c0644a4634d3f639b9796"
BANDS = ("large", "medium", "small")
# Frozen fallback chains, in order. Cursor uses the base names of its ACP session model option.
SEATS = {
    "claude": ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"),
    "codex": ("gpt-6.1-sol", "gpt-6-sol", "gpt-5.6-sol"),
    "cursor": ("grok-4.7", "grok-4.6", "composer-2.5"),
    "antigravity": ("gemini-4-argon-high", "gemini-4-argon-medium", "gemini-3.8-flash-high"),
}
JUDGES = tuple(SEATS)
MIN_PARSED = 19
LABELS = {"usable", "poor_crop", "wrong_target", "no_bird"}
FROZEN = ("rule-frozen-20261026.json", "cohort-frozen-20261026.json",
          "exclusions-frozen-20261026.json", "sample-frozen-20261026.json")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def inside(root, name):
    path = (Path(root) / str(name).replace("\\", "/")).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("artifact path escapes its local root")
    return path


def verify_hashes(root, files):
    if not files:
        raise ValueError("missing artifact hashes")
    for name, digest in files.items():
        if sha256(inside(root, name)) != digest:
            raise ValueError(f"artifact hash mismatch: {name}")


def verify_blind_files(repo, item, hashes):
    """Check neutral evidence filenames and reject retained image metadata."""
    from PIL import Image

    token = item["id"]
    if not isinstance(token, str) or len(token) != 4 or token[0] != "v" or not token[1:].isdigit():
        raise ValueError("validation item ID is not a neutral token")
    wanted = [f"{token}_overview.jpg", f"{token}_crop.jpg"]
    if [inside(repo, p).name for p in item["files"]] != wanted:
        raise ValueError("validation evidence filenames are not neutral")
    for name in item["files"]:
        if name not in hashes:
            raise ValueError("validation image lacks frozen hash")
        path = inside(repo, name)
        if sha256(path) != hashes[name]:
            raise ValueError("validation image hash changed")
        with Image.open(path) as image:
            if image.getexif() or any(k.lower() in {"exif", "xmp", "xml:com.adobe.xmp", "comment"}
                                      for k in image.info):
                raise ValueError("validation image retains private metadata")


def verify_frozen(root):
    if sha256(root / "freeze-receipt-20261026.json") != FREEZE_SHA256:
        raise ValueError("freeze receipt changed")
    receipt = read_json(root / "freeze-receipt-20261026.json")
    if set(receipt["files"]) != set(FROZEN) or receipt["files"][FROZEN[0]] != RULE_SHA256:
        raise ValueError("unexpected frozen rule or input inventory")
    verify_hashes(root, receipt["files"])
    sample = read_json(root / FROZEN[3])["frames"]
    excluded = set(read_json(root / FROZEN[2])["ids"])
    ids = [r["image_id"] for r in sample]
    if (len(ids) != len(set(ids)) or len(ids) != 390 or set(ids) & excluded
            or Counter(r["band"] for r in sample) != Counter(dict.fromkeys(BANDS, 130))):
        raise ValueError("sample size, uniqueness, exclusions or bands changed")
    return receipt, sample


def parse_reply(text, expected_ids):
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if not isinstance(payload, dict) or not ({"images", "items"} & payload.keys()):
            continue
        if "images" in payload and "items" in payload:
            raise ValueError("ambiguous reply envelopes")
        rows = payload.get("images", payload.get("items"))
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError("invalid reply rows")
        ids = [r.get("id") for r in rows]
        if (any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids)
                or set(ids) != set(expected_ids)):
            raise ValueError("missing, duplicate or unexpected reply IDs")
        for row in rows:
            if (row.get("presence") not in {"bird", "no_bird", "unsure"}
                    or row.get("grade") not in {"usable", "poor_crop", "wrong_target", "unsure"}
                    or not isinstance(row.get("reason"), str)):
                raise ValueError("invalid reply fields")
        return {r["id"]: {k: r[k] for k in ("presence", "grade", "reason")} for r in rows}
    raise ValueError("no complete JSON reply")


def outcome(vote):
    if vote["presence"] == "no_bird":
        return "no_bird"
    if vote["presence"] == "bird" and vote["grade"] in LABELS:
        return vote["grade"]
    return None


def calibration_stats(votes, answers):
    if len(answers) != 20 or not set(votes) <= set(answers):
        raise ValueError("unexpected calibration IDs or answer count")
    correct = 0
    confusion = Counter()
    for token, owner in answers.items():
        label = outcome(votes[token]) if token in votes else None
        predicted = None if label is None else label == "usable"
        expected = owner["usable"]
        same = predicted is not None and predicted == expected
        correct += same
        confusion["tp" if same and expected else "tn" if same else "fn" if expected else "fp"] += 1
    return {"parsed": len(votes), "correct": correct, "total": 20,
            "qualified": len(votes) >= MIN_PARSED and correct >= 18, "confusion": dict(confusion)}


def qualify_seat(by_model, answers, chain):
    """Walk a seat's chain. Only a technical failure may reach the next model."""
    stats, allowed, bar_failed = {}, [], False
    for model in chain:
        if model not in by_model:
            continue
        if bar_failed:
            raise ValueError("fallback after a bar failure")
        stats[model] = calibration_stats(by_model[model], answers)
        if stats[model]["qualified"]:
            allowed.append(model)
        elif stats[model]["parsed"] >= MIN_PARSED and not allowed:
            bar_failed = True
    return stats, allowed


def seat_votes(by_model, allowed):
    """Merge a seat's votes, keeping only models that passed the control draw."""
    merged = {}
    for model, rows in by_model.items():
        if rows and model not in allowed:
            raise ValueError("vote from a model that did not qualify")
        if merged.keys() & rows.keys():
            raise ValueError("duplicate accepted judgments")
        merged.update(rows)
    return merged


def receipt_model(agent, judge, chains):
    model = judge.get("model")
    if model not in chains[agent]:
        raise ValueError("judge model outside its chain")
    reported = str(judge.get("reportedModel") or "").split("[")[0]
    if agent == "cursor" and judge["ok"] and reported != model:
        raise ValueError("session reported a different model")
    return model


def parse_time(value):
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("receipt time has no timezone")
    return moment


def bind_receipt(repo, judge, rubric, locked_at):
    """Tie one judge receipt to the locked draw: frozen rubric in what was sent, same model, started after the lock.

    Every swarm run records its requested task in request.json. CLI runs also record the full prompt in
    result.json; ACP runs (Cursor) don't, so the request is the record for them.
    """
    result_path = inside(repo, f"{judge['outputDir']}/result.json")
    request_path = inside(repo, f"{judge['outputDir']}/request.json")
    result, request = read_json(result_path), read_json(request_path)
    if rubric not in str(request.get("task") or ""):
        raise ValueError("receipt request lacks the frozen rubric")
    if "prompt" in result and rubric not in str(result.get("prompt") or ""):
        raise ValueError("receipt prompt lacks the frozen rubric")
    if result.get("model") != judge.get("model") or request.get("model") != judge.get("model"):
        raise ValueError("receipt model differs from its panel record")
    started = parse_time(result.get("startedAt"))
    if started < locked_at:
        raise ValueError("receipt started before the controls were locked")
    return {"started_at": started.isoformat(), "result_sha256": sha256(result_path),
            "request_sha256": sha256(request_path)}


def attempt_order(evidence, seat, chain):
    """A seat's models in start order. Each attempt must come later in the chain, with no overlap in time."""
    spans = {}
    for proof in evidence:
        if proof["agent"] != seat:
            continue
        moment = parse_time(proof["started_at"])
        first, last = spans.get(proof["model"], (moment, moment))
        spans[proof["model"]] = (min(first, moment), max(last, moment))
    ordered = sorted(spans, key=lambda model: spans[model][0])
    for earlier, later in zip(ordered, ordered[1:]):
        if chain.index(later) <= chain.index(earlier) or spans[earlier][1] > spans[later][0]:
            raise ValueError("seat attempts out of chain order")
    return ordered


def qualify_seat_in_time(by_model, answers, ordered):
    """Attempts in start order. After a scored bar failure, later attempts are rejected and the seat stays failed."""
    stats, allowed, rejected, ended = {}, [], [], False
    for model in ordered:
        if ended:
            rejected.append(model)
            continue
        stats[model] = calibration_stats(by_model.get(model, {}), answers)
        if stats[model]["qualified"]:
            allowed.append(model)
        elif stats[model]["parsed"] >= MIN_PARSED and not allowed:
            ended = True
    return stats, allowed, rejected


def collect_panels(repo, panel_paths, items, allowed_judges, chains=None, binding=None):
    """Check image identity and raw receipts before accepting any batch votes.

    With chains, votes are grouped by seat and then by model. With binding (rubric, locked_at),
    every receipt must also pass bind_receipt.
    """
    expected = {r["id"]: r for r in items}
    if len(expected) != len(items):
        raise ValueError("duplicate manifest IDs")
    votes = {j: {} for j in allowed_judges}
    seen, evidence, failures = set(), [], []
    for panel_path in panel_paths:
        panel_path = inside(repo, panel_path)
        if panel_path in seen:
            raise ValueError("reused panel receipt")
        seen.add(panel_path)
        panel = read_json(panel_path)
        batch = panel["stages"]["build"]["items"]
        ids = [r["id"] for r in batch]
        if not ids or len(ids) > 10 or len(set(ids)) != len(ids) or not set(ids) <= expected.keys():
            raise ValueError("unexpected panel batch")
        for row in batch:
            actual = [inside(repo, p) for p in row["files"]]
            wanted = [inside(repo, p) for p in expected[row["id"]]["files"]]
            if actual != wanted:
                raise ValueError("panel image manifest mismatch")
        for judge in panel["stages"]["run"]["judges"]:
            agent = judge["agent"]
            if agent not in votes:
                raise ValueError("unexpected judge in panel")
            raw = inside(repo, judge["outputFile"])
            if raw in seen:
                raise ValueError("reused raw receipt")
            seen.add(raw)
            proof = {"agent": agent, "file": str(raw.relative_to(repo)), "sha256": sha256(raw)}
            bucket = votes[agent]
            if chains is not None:
                proof["model"] = receipt_model(agent, judge, chains)
                bucket = votes[agent].setdefault(proof["model"], {})
            if binding is not None:
                proof.update(bind_receipt(repo, judge, *binding))
            evidence.append(proof)
            if not judge["ok"]:
                failures.append({**proof, "error": "nonzero run"})
                continue
            try:
                batch_votes = parse_reply(raw.read_text(encoding="utf-8"), set(ids))
            except ValueError as exc:
                failures.append({**proof, "error": str(exc)})
                continue
            if bucket.keys() & batch_votes.keys():
                raise ValueError("duplicate accepted judgments")
            bucket.update(batch_votes)
    return votes, evidence, failures


def resolve_votes(votes, adjudication=None):
    if len(votes) < 3:
        raise ValueError("at least three qualified judges required")
    counts = Counter(label for v in votes.values() if v is not None and (label := outcome(v)) is not None)
    threshold = 2 if len(votes) == 3 else 3
    agreed = [label for label, n in counts.items() if n >= threshold]
    if len(agreed) == 1:
        return agreed[0]
    if adjudication:
        confidence = adjudication.get("confidence")
        if (type(confidence) in (float, int) and math.isfinite(confidence) and 0.7 <= confidence <= 1
                and adjudication.get("label") in LABELS):
            return adjudication["label"]
    return None


def analyze_bands(frames, labels):
    from scripts.research.detector_benchmark.v1_promotion_gate import wilson

    ids = [r["id"] for r in frames]
    if (len(ids) != len(set(ids)) or set(ids) != set(labels)
            or Counter(r["band"] for r in frames) != Counter(dict.fromkeys(BANDS, 130))
            or any(v is not None and v not in LABELS for v in labels.values())):
        raise ValueError("incomplete or invalid frozen validation set")

    def summarize(rows):
        resolved = [labels[r["id"]] for r in rows if labels[r["id"]] is not None]
        usable = resolved.count("usable")
        return {"total": len(rows), "resolved": len(resolved), "usable": usable,
                "unresolved": len(rows) - len(resolved), "wilson": wilson(usable, len(resolved)),
                "conservative_wilson": wilson(usable, len(rows))}

    result = {}
    for band in BANDS:
        rows = [r for r in frames if r["band"] == band]
        folders = {}
        for row in rows:  # Preserve the frozen seeded order; sensitivity is not a new sample.
            folders.setdefault(row["folder_id"], row)
        metrics = summarize(rows)
        metrics.update(passed=metrics["wilson"][0] >= 0.9,
                       use="geometry_only" if band == "small" else "region_species",
                       one_per_folder=summarize(list(folders.values())))
        result[band] = metrics
    return result



def owner_bands(sample, items, record, delegated_unresolved=False):
    """Owner-labelled route (2026-11-09): all 13 batches, every frame once, ``unsure`` unresolved.

    ``delegated_unresolved`` is the amendment's sensitivity: judge/Jev verdicts count as unresolved.
    """
    from scripts.research.detector_benchmark import promotion_694_owner as owner

    batches = [b["batch"] for b in record["batches"]]
    rows = [row for b in record["batches"] for row in b["rows"]]
    batch_of = {r["token"]: r["batch"] for r in items}
    if batches != list(range(1, owner.BATCHES + 1)) or sorted(r["token"] for r in rows) != sorted(batch_of):
        raise ValueError("the owner record must cover all 390 frames in 13 batches")
    for b in record["batches"]:
        if any(row["batch"] != b["batch"] or batch_of[row["token"]] != b["batch"] for row in b["rows"]):
            raise ValueError("owner record row is in the wrong batch")
    if any(row["label"] not in owner.LABEL_CHOICES for row in rows):
        raise ValueError("unknown owner label")
    labels = {row["token"]: None if row["label"] == "unsure" or (delegated_unresolved and row.get("resolved_by"))
              else row["label"] for row in rows}
    token = {r["image_id"]: r["token"] for r in items}
    frames = [{"id": token[r["image_id"]], "band": r["band"], "folder_id": r["folder_id"]} for r in sample]
    return analyze_bands(frames, labels)


def owner_report(root, repo, sample, frozen, record_path):
    from scripts.research.detector_benchmark import promotion_694_owner as owner

    items = owner.load_frozen(root, sample)
    manifest = read_json(root / owner.MANIFEST)
    if manifest["freeze_sha256"] != owner.FREEZE_SHA256 or [r["id"] for r in manifest["items"]] != [
            r["token"] for r in items]:
        raise ValueError("owner sample manifest belongs to a different freeze or order")
    by_id = {r["image_id"]: r for r in sample}
    for row, item in zip(manifest["items"], items):
        if row["image_id"] != item["image_id"] or any(
                row[k] != by_id[row["image_id"]][k] for k in ("band", "folder_id", "run_id", "region_id",
                                                               "rendition_hash")):
            raise ValueError("owner sample identity changed")
        verify_blind_files(repo, row, manifest["sha256"])
    record = read_json(record_path)
    return {"status": "analyzed", "route": "owner_labels", "bands": owner_bands(sample, items, record),
            "delegated": sum(bool(r.get("resolved_by")) for b in record["batches"] for r in b["rows"]),
            "bands_delegated_unresolved": owner_bands(sample, items, record, delegated_unresolved=True),
            "record_sha256": sha256(record_path), "manifest_sha256": sha256(root / owner.MANIFEST),
            "owner_freeze_sha256": owner.FREEZE_SHA256, "frozen_files": frozen["files"], "promotions": 0}

def verify_amendment(root):
    path = root / "freeze-receipt-judges-20261105.json"
    if sha256(path) != JUDGE_FREEZE_SHA256:
        raise ValueError("judge freeze receipt changed")
    receipt = read_json(path)
    if (receipt["amendment_sha256"] != AMENDMENT_SHA256
            or sha256(inside(root, receipt["amendment"])) != AMENDMENT_SHA256):
        raise ValueError("judge amendment changed")


def calibration_report(root, repo, panels):
    frozen, _ = verify_frozen(root)
    verify_amendment(root)
    if sha256(root / "calibration-r2-manifest-20261105.json") != CALIBRATION_SHA256:
        raise ValueError("calibration image manifest changed")
    manifest = read_json(root / "calibration-r2-manifest-20261105.json")
    if manifest["rule_sha256"] != RULE_SHA256:
        raise ValueError("calibration rule changed")
    verify_hashes(root / "calibration-r2-blind-20261105", manifest["sha256"])
    key = root / "calibration-r2-answer-key-20261105.json"
    if sha256(key) != ANSWER_SHA256:
        raise ValueError("owner answer key changed")
    answers = read_json(key)
    if set(answers) != {r["id"] for r in manifest["items"]}:
        raise ValueError("calibration manifest IDs changed")
    votes, evidence, failures = collect_panels(repo, panels, manifest["items"], JUDGES, chains=SEATS)
    stats, allowed = {}, {}
    for judge, chain in SEATS.items():
        stats[judge], allowed[judge] = qualify_seat(votes[judge], answers, chain)
    qualified = [j for j in JUDGES if allowed[j]]
    return {"status": "qualified" if len(qualified) >= 3 else "blocked_insufficient_judges",
            "stats": stats, "qualified_judges": qualified, "allowed_models": allowed,
            "frozen_files": frozen["files"], "evidence": evidence,
            "failures": failures, "owner_labels_unchanged": True, "fresh_validation_labels": 0}


def verify_r3_lock(root):
    """Check the rubric freeze, replay the owner's label validation, and check the locked draw against both."""
    from scripts.research.detector_benchmark import promotion_694_controls as controls

    if sha256(root / controls.FREEZE) != R3_FREEZE_SHA256:
        raise ValueError("rubric freeze receipt changed")
    freeze, candidates, stored, _ = controls.load_frozen(root)
    if sha256(inside(root, freeze["amendment"])) != freeze["amendment_sha256"]:
        raise ValueError("rubric amendment changed")
    lock_path = root / controls.LOCK
    files, locked_at = _read_lock(root, lock_path, freeze)
    state = controls.replay(candidates, read_json(inside(root, files["validation"]["path"]))["reviews"], stored)
    return _check_locked_draw(root, lock_path, files, locked_at, state, freeze, root / controls.BLIND)


def _read_lock(root, lock_path, freeze):
    lock = read_json(lock_path)
    files = lock["files"]
    verify_hashes(root, {entry["path"]: entry["sha256"] for entry in files.values()})
    if files["rubric"]["sha256"] != freeze["rubric_sha256"]:
        raise ValueError("locked rubric differs from the frozen rubric")
    locked_at = parse_time(lock["locked_at"])
    if locked_at <= parse_time(freeze["frozen_at"]):
        raise ValueError("lock precedes the freeze")
    return files, locked_at


def _check_locked_draw(root, lock_path, files, locked_at, state, freeze, blind_dir):
    """The answer key must equal the replayed confirmed controls, and the manifest and images must match it."""
    if not state["complete"]:
        raise ValueError("label validation is not complete")
    answers = read_json(inside(root, files["answer_key"]["path"]))
    confirmed = {(stratum, image_id) for stratum, ids in state["confirmed"].items() for image_id in ids}
    if len(answers) != 20 or {(a["grade"], a["image_id"]) for a in answers.values()} != confirmed:
        raise ValueError("answer key differs from the confirmed controls")
    if any(a["usable"] != (a["grade"] == "usable") for a in answers.values()):
        raise ValueError("answer key usable flag differs from its grade")
    manifest = read_json(inside(root, files["manifest"]["path"]))
    if {r["id"] for r in manifest["items"]} != set(answers) or manifest["rubric_sha256"] != freeze["rubric_sha256"]:
        raise ValueError("manifest differs from the answer key or the frozen rubric")
    verify_hashes(blind_dir, manifest["sha256"])
    rubric = inside(root, freeze["rubric"]).read_text(encoding="utf-8").strip()
    return {"answers": answers, "manifest": manifest, "locked_at": locked_at, "rubric": rubric,
            "lock_sha256": sha256(lock_path)}


def verify_rev3_lock(root):
    """Revision 3: check both freezes, replay round 1 and the later rounds, and check the locked draw."""
    from scripts.research.detector_benchmark import promotion_694_controls as controls

    if sha256(root / controls.FREEZE4) != REV3_FREEZE_SHA256:
        raise ValueError("revision 3 freeze receipt changed")
    if sha256(root / controls.FREEZE) != R3_FREEZE_SHA256:
        raise ValueError("rubric freeze receipt changed")
    freeze, candidates, batch, stored, round1, _ = controls.load_frozen_rev3(root)
    lock_path = root / controls.LOCK4
    files, locked_at = _read_lock(root, lock_path, freeze)
    if files["round1"]["sha256"] != freeze["round1_validation_sha256"]:
        raise ValueError("locked round 1 record differs from the frozen one")
    later = read_json(inside(root, files["round2"]["path"]))["reviews"]
    state = controls.replay_rev3(candidates, batch, round1, later, stored)
    return _check_locked_draw(root, lock_path, files, locked_at, state, freeze, root / controls.BLIND4)


def calibration_report_r3(root, repo, panels):
    """One control draw per seat under revision 3 (2026-11-09), with receipts bound to the locked draw."""
    locked = verify_rev3_lock(root)
    votes, evidence, failures = collect_panels(repo, panels, locked["manifest"]["items"], JUDGES, chains=SEATS,
                                               binding=(locked["rubric"], locked["locked_at"]))
    stats, allowed, rejected = {}, {}, {}
    for judge, chain in SEATS.items():
        ordered = attempt_order(evidence, judge, chain)
        stats[judge], allowed[judge], rejected[judge] = qualify_seat_in_time(votes[judge], locked["answers"], ordered)
    qualified = [j for j in JUDGES if allowed[j]]
    return {"status": "qualified" if len(qualified) >= 3 else "blocked_insufficient_judges",
            "stats": stats, "qualified_judges": qualified, "allowed_models": allowed,
            "rejected_fallbacks": rejected, "lock_sha256": locked["lock_sha256"], "evidence": evidence,
            "failures": failures, "owner_labels_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(".agent/scratch/promotion-694"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    owner_cmd = sub.add_parser("analyze-owner")
    owner_cmd.add_argument("--record", type=Path, required=True)
    owner_cmd.add_argument("--output", type=Path, required=True)
    for action in ("calibrate", "analyze", "calibrate-r3"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--panel", type=Path, action="append", required=True)
        cmd.add_argument("--output", type=Path, required=True)
        if action == "analyze":
            cmd.add_argument("--calibration", type=Path, required=True)
            cmd.add_argument("--manifest", type=Path, required=True)
            cmd.add_argument("--adjudications", type=Path)
    args = parser.parse_args()
    root, repo = args.root.resolve(), Path(__file__).resolve().parents[3]
    frozen, sample = verify_frozen(root)
    verify_amendment(root)
    if args.command == "verify":
        print(json.dumps({"status": "verified", "frames": len(sample), "files": frozen["files"]}))
        return
    if args.command == "analyze-owner":
        result = owner_report(root, repo, sample, frozen, args.record)
    elif args.command == "calibrate":
        result = calibration_report(root, repo, args.panel)
    elif args.command == "calibrate-r3":
        result = calibration_report_r3(root, repo, args.panel)
    else:
        # Recompute qualification from the recorded raw replies, never trust an edited pass flag.
        prior = read_json(args.calibration)
        panel_paths = prior.get("panels", [])
        if not panel_paths:
            raise ValueError("calibration receipt lacks panel provenance")
        calibration = calibration_report(root, repo, panel_paths)
        if calibration["status"] != "qualified" or calibration["evidence"] != prior.get("evidence"):
            raise ValueError("at least three qualified judges with intact receipts required")
        manifest = read_json(args.manifest)
        if manifest["frozen_files"] != frozen["files"]:
            raise ValueError("validation manifest belongs to different frozen inputs")
        verify_hashes(repo, manifest["sha256"])
        items = manifest["items"]
        by_id = {r["image_id"]: r for r in sample}
        if len(items) != 390 or len({r["image_id"] for r in items}) != 390:
            raise ValueError("validation manifest has incorrect sample coverage")
        for row in items:
            if row["image_id"] not in by_id:
                raise ValueError("validation image outside frozen sample")
            for key in ("band", "folder_id", "run_id", "region_id", "rendition_hash"):
                if row[key] != by_id[row["image_id"]][key]:
                    raise ValueError("validation identity changed")
            verify_blind_files(repo, row, manifest["sha256"])
        qualified = calibration["qualified_judges"]
        votes, evidence, failures = collect_panels(repo, args.panel, items, qualified, chains=SEATS)
        merged = {j: seat_votes(votes[j], calibration["allowed_models"][j]) for j in qualified}
        adjudications = read_json(args.adjudications) if args.adjudications else {}
        if not set(adjudications) <= {r["id"] for r in items}:
            raise ValueError("adjudication outside validation manifest")
        labels, disputes = {}, []
        for item in items:
            token = item["id"]
            row_votes = {j: merged[j].get(token) for j in qualified}
            labels[token] = resolve_votes(row_votes, adjudications.get(token))
            if resolve_votes(row_votes) is None:
                disputes.append({"id": token, "votes": row_votes})
        result = {"status": "analyzed", "bands": analyze_bands(items, labels),
                  "labels": labels, "disputes": disputes, "evidence": evidence, "failures": failures,
                  "frozen_files": frozen["files"], "promotions": 0}
        result["calibration_sha256"] = sha256(args.calibration)
        result["adjudications_sha256"] = sha256(args.adjudications) if args.adjudications else None
    if args.command != "analyze-owner":
        result["panels"] = [str(inside(repo, p).relative_to(repo)) for p in args.panel]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
