"""Reservation import fails closed when original receipt evidence is missing or changed."""
import hashlib
import json

import pytest

from modules import localization_authority_reservations as inventory


def test_unrecognized_receipt_cannot_reserve_or_unreserve_images(tmp_path):
    (tmp_path / "freeze-receipt-20261026.json").write_text("{}")
    with pytest.raises(ValueError, match="receipt hash mismatch"):
        inventory.read_frozen_inventory(tmp_path)


def synthetic_inventory(tmp_path, monkeypatch, *, images=None):
    # Only this explicit test fixture replaces the pinned receipt/rule hashes.
    cohort = {"rule_sha256": "a" * 64, "images": images or [{"image_id": 1, "run_id": 2, "region_id": 3}]}
    files = {name: b"{}" for name in inventory.FILES}
    files[inventory.FILES[1]] = json.dumps(cohort).encode()
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    cohort["rule_sha256"] = hashes[inventory.FILES[0]]
    files[inventory.FILES[1]] = json.dumps(cohort).encode()
    hashes[inventory.FILES[1]] = hashlib.sha256(files[inventory.FILES[1]]).hexdigest()
    receipt = json.dumps({"files": hashes, "cohort": len(cohort["images"])}).encode()
    for name, raw in files.items():
        (tmp_path / name).write_bytes(raw)
    (tmp_path / "freeze-receipt-20261026.json").write_bytes(receipt)
    monkeypatch.setattr(inventory, "FROZEN_RECEIPT_SHA256", hashlib.sha256(receipt).hexdigest())
    monkeypatch.setattr(inventory, "R2_RULE_SHA256", hashes[inventory.FILES[0]])
    return hashes


def test_verified_inventory_retains_image_and_original_artifact_identities(tmp_path, monkeypatch):
    hashes = synthetic_inventory(tmp_path, monkeypatch)
    digest, rows = inventory.read_frozen_inventory(tmp_path)
    assert digest == hashes[inventory.FILES[1]]
    assert rows == [{"image_id": 1, "run_id": 2, "region_id": 3}]


@pytest.mark.parametrize("name", inventory.FILES)
def test_each_frozen_input_is_hash_checked(tmp_path, monkeypatch, name):
    synthetic_inventory(tmp_path, monkeypatch)
    (tmp_path / name).write_text("changed")
    with pytest.raises(ValueError, match="input changed"):
        inventory.read_frozen_inventory(tmp_path)


def test_duplicate_image_reservations_fail_validation(tmp_path, monkeypatch):
    synthetic_inventory(tmp_path, monkeypatch, images=[{"image_id": 1, "run_id": 2, "region_id": 3}] * 2)
    with pytest.raises(ValueError, match="duplicate"):
        inventory.read_frozen_inventory(tmp_path)
