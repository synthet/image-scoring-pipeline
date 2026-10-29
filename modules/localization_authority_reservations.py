"""Import image-level reservations only from the intact registered #694 inventory."""
import hashlib
import json
from pathlib import Path

from modules.localization_evaluation import R2_RULE_SHA256

FROZEN_RECEIPT_SHA256 = "acc44121e591e24477a65e49f12e13cc63ac8836d1ddba2c4bfdf3d3bdafe170"
FILES = ("rule-frozen-20261026.json", "cohort-frozen-20261026.json",
         "exclusions-frozen-20261026.json", "sample-frozen-20261026.json")


def read_frozen_inventory(root):
    root = Path(root)
    raw = (root / "freeze-receipt-20261026.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_RECEIPT_SHA256:
        raise ValueError("frozen reservation receipt hash mismatch")
    receipt = json.loads(raw)
    if set(receipt["files"]) != set(FILES) or receipt["files"][FILES[0]] != R2_RULE_SHA256:
        raise ValueError("unexpected frozen inventory")
    contents = {}
    for name in FILES:
        content = (root / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != receipt["files"][name]:
            raise ValueError(f"frozen reservation input changed: {name}")
        contents[name] = json.loads(content)
    cohort = contents[FILES[1]]
    if cohort["rule_sha256"] != R2_RULE_SHA256 or len(cohort["images"]) != receipt["cohort"]:
        raise ValueError("frozen cohort identity mismatch")
    rows = []
    seen = set()
    for row in cohort["images"]:
        evidence = {key: row[key] for key in ("image_id", "run_id", "region_id")}
        if any(type(value) is not int or value <= 0 for value in evidence.values()):
            raise ValueError("invalid frozen identity")
        if evidence["image_id"] in seen:
            raise ValueError("duplicate frozen image ID")
        seen.add(evidence["image_id"])
        rows.append(evidence)
    return receipt["files"][FILES[1]], rows


def import_frozen_reservations(store, root):
    """No timeout/release path. Evidence survives repair, new runs and deletion."""
    inventory_hash, rows = read_frozen_inventory(root)

    def apply(tx):
        control = tx.query_one("SELECT * FROM localization_authority_control WHERE id=1 FOR UPDATE")
        for row in rows:
            tx.execute(
                "INSERT INTO localization_authority_reservations "
                "(inventory_sha256,image_id,original_run_id,original_region_id,evidence) "
                "VALUES (?,?,?,?,?::jsonb) ON CONFLICT DO NOTHING",
                (inventory_hash, row["image_id"], row["run_id"], row["region_id"], json.dumps(row)),
            )
        if control["reservation_inventory_sha256"] != inventory_hash:
            tx.execute(
                "UPDATE localization_authority_control SET reservation_inventory_sha256=?,"
                "revision=revision+1,scan_cursor=0,updated_at=clock_timestamp() WHERE id=1", (inventory_hash,),
            )
        return {"inventory_sha256": inventory_hash, "reserved_images": len(rows)}
    return store.conn.run_transaction(apply)
