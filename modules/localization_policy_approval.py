"""Explicit scoped qualification receipts; no synthetic/force production override."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from modules.localization_authority_store import fingerprint
from modules.localization_evaluation import ArtifactScope, R2_RULE_ID, R2_RULE_SHA256

RUNTIME_RULE_ID = "bird-authority-runtime-rule/1"
RUNTIME_RULE = {
    "id": RUNTIME_RULE_ID, "geometry_interpreter": R2_RULE_SHA256,
    "population": "current_display_bird", "replace": "policy_owned_only",
    "species_min_area": 0.005, "independent_discovery": True,
}
RUNTIME_RULE_SHA256 = fingerprint(RUNTIME_RULE)


def register_runtime_policy(store, scope: ArtifactScope):
    values = asdict(scope)
    if any(not isinstance(v, str) or not v.strip() for v in values.values()):
        raise ValueError("complete producer scope required")
    key = fingerprint({"schema": "runtime-authority/1", "rule": RUNTIME_RULE_SHA256, "scope": values})

    def register(tx):
        tx.query_one("SELECT id FROM localization_authority_control WHERE id=1 FOR UPDATE")
        count = tx.execute(
            "INSERT INTO localization_authority_policies (policy_hash,rule_id,rule_sha256,scope,rule_kind) "
            "VALUES (?,?,?,?::jsonb,'runtime') ON CONFLICT DO NOTHING",
            (key, RUNTIME_RULE_ID, RUNTIME_RULE_SHA256, json.dumps(values)),
        )
        if count:
            tx.execute("UPDATE localization_authority_control SET revision=revision+1,scan_cursor=0 WHERE id=1")
        return key
    return store.conn.run_transaction(register)


def wilson_lower(usable, total):
    if not total:
        return 0.0
    z = 1.959963984540054
    p = usable / total
    return (p+z*z/(2*total)-z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))) / (1+z*z/total)


def validate_qualification(path, expected_sha256, policy):
    supported = {'r2': (R2_RULE_ID, R2_RULE_SHA256), 'runtime': (RUNTIME_RULE_ID, RUNTIME_RULE_SHA256)}
    if supported.get(policy['rule_kind']) != (policy['rule_id'], policy['rule_sha256']):
        raise ValueError("unknown qualification policy")
    path = Path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("qualification receipt hash mismatch")
    receipt = json.loads(raw)
    if (receipt.get("schema") != "localization-qualification/1" or receipt.get("source_kind") != "real_holdout"
            or receipt.get("synthetic") or receipt.get("policy_hash") != policy["policy_hash"]
            or receipt.get("rule_sha256") != policy["rule_sha256"] or receipt.get("scope") != policy["scope"]):
        raise ValueError("qualification identity/scope mismatch")
    sources = receipt.get("source_receipts") or {}
    if len(sources) < 3:
        raise ValueError("raw qualification provenance required")
    for name, digest in sources.items():
        source = (path.parent / name).resolve()
        if not source.is_relative_to(path.parent.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("qualification evidence changed")
    def evidence(name):
        if not isinstance(name, str) or name not in sources:
            raise ValueError("unbound qualification evidence")
        return json.loads((path.parent / name).read_bytes())

    manifest = evidence(receipt.get("validation_manifest"))
    if manifest.get("rule_sha256") != policy["rule_sha256"] or manifest.get("scope") != policy["scope"]:
        raise ValueError("validation manifest scope mismatch")
    judges = receipt.get("judges") or []
    names = [j.get("name") for j in judges]
    if len(names) < 3 or any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
        raise ValueError("three distinct calibrated judges required")
    for judge in judges:
        controls = judge.get("controls") or []
        raw_judge = evidence(judge.get("raw_file"))
        if (raw_judge.get("schema") != "localization-judge-receipt/1" or raw_judge.get("judge") != judge["name"]
                or raw_judge.get("controls") != controls
                or [{k:v for k,v in c.items() if k!='predicted'} for c in controls] != manifest.get("controls")):
            raise ValueError("calibration evidence mismatch")
        if (len(controls) != 20 or len({c.get("id") for c in controls}) != 20
                or sum(c.get("predicted") is not None for c in controls) < 19
                or sum(c.get("predicted") == c.get("expected") and c.get("expected") is not None for c in controls) < 18):
            raise ValueError("judge calibration failed")
    labels = receipt.get("labels") or []
    ids = [row.get("image_id") for row in labels]
    if len(ids) != len(set(ids)) or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("invalid validation identities")
    identities = ("image_id","run_id","region_id","rendition_hash","band")
    def identity(rows):
        return {r["image_id"]: {k:r.get(k) for k in identities} for r in rows}
    frames = manifest.get("frames") or []
    if len(frames) != len(labels) or len(identity(frames)) != len(frames) or identity(frames) != identity(labels):
        raise ValueError("validation artifact identity mismatch")
    for judge in judges:
        if evidence(judge["raw_file"]).get("votes") != {str(r["image_id"]):r.get("votes",{}).get(judge["name"]) for r in labels}:
            raise ValueError("validation votes differ from raw evidence")
    if policy["rule_kind"] == "r2":
        from modules.localization_authority_reservations import read_frozen_inventory
        read_frozen_inventory(path.parent)
        frozen = json.loads((path.parent / "sample-frozen-20261026.json").read_text(encoding="utf-8"))["frames"]
        if identity(frozen) != identity(labels):
            raise ValueError("validation differs from frozen R2 sample")
        answer = path.parent / "calibration-answer-key-20261026.json"
        if hashlib.sha256(answer.read_bytes()).hexdigest() != "f60e9ad7a21ee68f2e2a1985dd37528e69b1cb44c00606f61a90ce909c20a76c":
            raise ValueError("calibration owner key changed")
        expected = {k:v["usable"] for k,v in json.loads(answer.read_bytes()).items()}
        if expected != {c["id"]:c["expected"] for c in manifest["controls"]}:
            raise ValueError("calibration owner labels mismatch")
    bands = receipt.get("geometry_bands") or []
    if not bands or len(set(bands)) != len(bands) or not set(bands) <= {"small", "medium", "large"}:
        raise ValueError("explicit qualified geometry bands required")
    species_bands = receipt.get("species_bands") or []
    if (type(receipt.get("species_allowed",False)) is not bool or
            (receipt.get("species_allowed") and (not species_bands or not set(species_bands) <= set(bands)&{"medium","large"}))):
        raise ValueError("species approval exceeds qualified area bands")
    for band in bands:
        rows = [r for r in labels if r.get("band") == band]
        if len(rows) != 130:
            raise ValueError("registered 130-per-band validation required")
        resolved = []
        for row in rows:
            votes = row.get("votes") or {}
            if set(votes) != set(names) or not set(votes.values()) <= {"usable","poor_crop","wrong_target","no_bird",None}:
                raise ValueError("incomplete validation votes")
            counts = Counter(v for v in votes.values() if v is not None)
            agreed = [v for v, n in counts.items() if n >= 3 or (len(names) == 3 and n >= 2)]
            if len(agreed) == 1:
                resolved.append(agreed[0])
        if wilson_lower(resolved.count("usable"), len(resolved)) < 0.90:
            raise ValueError("geometry qualification failed")
    return receipt
