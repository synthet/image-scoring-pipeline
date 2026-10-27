"""Exact-manifest removal, isolated from scoring. Default mode is read-only dry-run.

Filesystem and database changes cannot share a transaction. A durable write-ahead
journal, verified copies, frozen row evidence, and idempotent DB operations bridge
that boundary. This module never discovers extra deletion targets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil

from .file_delete import delete_exact
from .locks import acquire, release


class SafetyError(RuntimeError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def durable_write(path, data):
    with Path(path).open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def sync_file(path):
    with Path(path).open("r+b") as f:
        os.fsync(f.fileno())


def checked_path(path, roots):
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts:
        raise SafetyError("Expected an exact absolute path without traversal")
    resolved = p.resolve()
    if p.is_symlink() or not any(resolved.parent == Path(r).resolve() for r in roots):
        raise SafetyError("Target escapes an authorized shoot directory")
    # resolve() also catches symlink/junction ancestors escaping the source.
    if os.path.normcase(str(p.absolute())) != os.path.normcase(str(resolved)):
        raise SafetyError("Source aliases/junctions require explicit reconciliation")
    return p


def canonical_file_identity(value):
    value = str(value).replace("\\", "/")
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", value)
    if match:
        value = match[1] + ":/" + match[2]
    if re.match(r"^[a-zA-Z]:/", value):
        return value.lower().rstrip("/")
    return os.path.normcase(value).rstrip("/")


def validate_manifest(manifest, roots):
    if (
        manifest.get("schema") != "neardupe-removal/1"
        or manifest.get("validation_status") != "audited"
    ):
        raise SafetyError("Only a frozen audited removal manifest can be applied")
    entries = manifest.get("entries", [])
    ids = [r["image_id"] for r in entries]
    if len(ids) != len(set(ids)):
        raise SafetyError("Duplicate image IDs in removal manifest")
    removed = set(ids)
    paths = []
    for row in entries:
        if (
            row.get("protected_reasons")
            or not row.get("judge_keys")
            or not row.get("audit_receipt")
            or row["replacement_id"] in removed
            or row["replacement_id"] == row["image_id"]
        ):
            raise SafetyError(
                "Missing validation, protected source or replacement cycle"
            )
        p = checked_path(row["path"], roots)
        if p.suffix.lower() != ".nef":
            raise SafetyError("Removal root must be an exact RAW")
        replacement = checked_path(row["replacement_path"], roots)
        if replacement.suffix.lower() != ".nef":
            raise SafetyError("Replacement must be an exact RAW")
        if canonical_file_identity(row.get("db_path", "")) != canonical_file_identity(
            p
        ) or canonical_file_identity(
            row.get("replacement_db_path", "")
        ) != canonical_file_identity(replacement):
            raise SafetyError("Database and disk paths identify different photographs")
        paths.append(os.path.normcase(str(p)))
        for side in row.get("sidecars", []):
            s = checked_path(side["path"], roots)
            if (
                s.parent != p.parent
                or s.stem.lower() not in (p.stem.lower(), p.name.lower())
                or s.suffix.lower()
                not in (".xmp", ".dop", ".acr", ".on1", ".pp3", ".cos", ".nksc")
            ):
                raise SafetyError("Sidecar association is not exact")
            paths.append(os.path.normcase(str(s)))
        for obj in [row, *row.get("sidecars", [])]:
            if len(obj.get("sha256", "")) != 64:
                raise SafetyError("Every target needs a frozen original hash")
        if len(row.get("replacement_sha256", "")) != 64:
            raise SafetyError("Replacement hash missing")
    if len(paths) != len(set(paths)):
        raise SafetyError("A source file appears more than once")
    return entries


class Executor:
    def __init__(self, manifest_path, backup, db, roots):
        self.manifest_path = Path(manifest_path)
        self.manifest_bytes = self.manifest_path.read_bytes()
        self.digest = hashlib.sha256(self.manifest_bytes).hexdigest()
        self.manifest = json.loads(self.manifest_bytes)
        self.entries = validate_manifest(self.manifest, roots)
        self.backup = Path(backup)
        self.db = db
        self.journal = self.backup / "journal.jsonl"
        self.roots = roots
        for root in roots:
            if self.backup.resolve().is_relative_to(Path(root).resolve()):
                raise SafetyError("Backup must be outside the selected shoot folders")

    def events(self, allow_incomplete_tail=False, repair_tail=False):
        if not self.journal.exists():
            return []
        result = []
        data = self.journal.read_bytes()
        lines = data.splitlines(keepends=True)
        valid_bytes = 0
        for index, line in enumerate(lines):
            try:
                event = json.loads(line)
            except ValueError as e:
                if (
                    allow_incomplete_tail
                    and index == len(lines) - 1
                    and not line.endswith(b"\n")
                ):
                    if repair_tail:
                        durable_write(
                            self.backup
                            / (
                                "journal-tail-"
                                + hashlib.sha256(line).hexdigest()[:16]
                                + ".bin"
                            ),
                            line,
                        )
                        with self.journal.open("r+b") as f:
                            f.truncate(valid_bytes)
                            f.flush()
                            os.fsync(f.fileno())
                    break
                raise SafetyError(
                    "Truncated journal requires recovery, not blind resume"
                ) from e
            if event.get("manifest_sha256") != self.digest:
                raise SafetyError("Journal belongs to a different manifest")
            result.append(event)
            valid_bytes += len(line)
        return result

    def append(self, event, **data):
        record = {
            "event": event,
            "manifest_sha256": self.digest,
            "at": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        with self.journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def verify_backup_receipt(self):
        receipt = self.manifest.get("database_backup", {})
        if (
            receipt.get("isolated_restore_verified") is not True
            or receipt.get("source_identity") != self.db.identity()
            or not receipt.get("restore_receipt_sha256")
        ):
            raise SafetyError("Verified isolated PostgreSQL restoration is required")
        if sha256(receipt["dump_path"]) != receipt["dump_sha256"]:
            raise SafetyError("Database dump hash mismatch")
        if sha256(receipt["restore_receipt_path"]) != receipt["restore_receipt_sha256"]:
            raise SafetyError("Restoration receipt hash mismatch")

    def dry_run(self):
        self.db.assert_quiescent()
        report = []
        for row in self.entries:
            if (
                sha256(row["path"]) != row["sha256"]
                or sha256(row["replacement_path"]) != row["replacement_sha256"]
            ):
                raise SafetyError("Original or replacement changed")
            for side in row.get("sidecars", []):
                if sha256(side["path"]) != side["sha256"]:
                    raise SafetyError("Sidecar changed")
            self.db.check_identity(row)
            self.db.assert_removable(row)
            report.append(
                {
                    "image_id": row["image_id"],
                    "replacement_id": row["replacement_id"],
                    "bytes": row["size"],
                }
            )
        # No directory, lock, receipt, backup, file or DB mutation in dry-run.
        return {
            "mode": "dry-run",
            "manifest_sha256": self.digest,
            "entries": report,
            "mutations": 0,
        }

    def apply(self, resume=False):
        self.verify_backup_receipt()
        self.db.assert_quiescent()
        previous = self.events(allow_incomplete_tail=resume)
        if any(e["event"] == "recovered" for e in previous):
            raise SafetyError(
                "A recovered study requires a newly validated manifest before removal"
            )
        if self.journal.exists() and not resume:
            complete = {e["image_id"] for e in previous if e["event"] == "verified"}
            if complete != {r["image_id"] for r in self.entries}:
                raise SafetyError("Interrupted journal requires explicit resume")
        self.backup.mkdir(parents=True, exist_ok=True)
        lock = self.backup / "apply.lock"
        fd = acquire(lock)
        try:
            previous = self.events(allow_incomplete_tail=resume, repair_tail=resume)
            frozen = self.backup / "removal-manifest.json"
            if frozen.exists() and frozen.read_bytes() != self.manifest_bytes:
                raise SafetyError("Backup manifest identity mismatch")
            if not frozen.exists():
                durable_write(frozen, self.manifest_bytes)
            for row in self.entries:
                iid = row["image_id"]
                self.db.assert_quiescent()
                if sha256(row["replacement_path"]) != row["replacement_sha256"]:
                    raise SafetyError("Retained replacement changed or disappeared")
                if self.db.exists(iid):
                    # Human ground truth outranks any model redundancy verdict.
                    self.db.assert_removable(row)
                directory = self.backup / str(iid)
                directory.mkdir(exist_ok=True)
                done = any(
                    e["event"] == "verified" and e.get("image_id") == iid
                    for e in previous
                )
                objects = [row, *row.get("sidecars", [])]
                for obj in objects:
                    src = checked_path(obj["path"], self.roots)
                    dest = directory / src.name
                    if dest.exists():
                        if sha256(dest) != obj["sha256"]:
                            raise SafetyError(
                                "Existing recovery copy has the wrong hash"
                            )
                    else:
                        if not src.is_file() or sha256(src) != obj["sha256"]:
                            raise SafetyError("Unbacked source missing or changed")
                        temporary = directory / (src.name + ".partial")
                        if temporary.exists():
                            raise SafetyError("Incomplete backup requires inspection")
                        shutil.copy2(src, temporary)
                        if sha256(temporary) != obj["sha256"]:
                            raise SafetyError("Backup verification failed; source kept")
                        sync_file(temporary)
                        temporary.replace(dest)
                        self.append(
                            "file_backed_up",
                            image_id=iid,
                            path=str(src),
                            backup_path=str(dest),
                            sha256=obj["sha256"],
                        )
                if done:
                    if any(Path(o["path"]).exists() for o in objects) or self.db.exists(
                        iid
                    ):
                        raise SafetyError("Completed removal no longer matches journal")
                    continue
                if hasattr(self.db, "begin_batch"):
                    self.db.begin_batch(row)
                row_snapshot = directory / "rows.json"
                if row_snapshot.exists():
                    prior = [
                        e
                        for e in previous
                        if e["event"] == "rows_backed_up" and e.get("image_id") == iid
                    ]
                    if not prior:
                        # A crash here precedes all file-removal intents. Recheck
                        # both systems before accepting the unreceipted snapshot.
                        if not self.db.exists(iid) or any(
                            not Path(o["path"]).is_file()
                            or sha256(o["path"]) != o["sha256"]
                            for o in objects
                        ):
                            raise SafetyError(
                                "Unreceipted row evidence with changed source"
                            )
                        self.db.check_identity(row)
                        if json.loads(
                            row_snapshot.read_text(encoding="utf-8")
                        ) != json.loads(json.dumps(self.db.snapshot(row), default=str)):
                            raise SafetyError(
                                "Unreceipted row evidence differs from live database"
                            )
                        sync_file(row_snapshot)
                        self.append(
                            "rows_backed_up",
                            image_id=iid,
                            path=str(row_snapshot),
                            sha256=sha256(row_snapshot),
                        )
                    elif sha256(row_snapshot) != prior[-1]["sha256"]:
                        raise SafetyError("Row recovery evidence changed")
                elif self.db.exists(iid):
                    self.db.check_identity(row)
                    durable_write(
                        row_snapshot,
                        json.dumps(self.db.snapshot(row), default=str).encode(),
                    )
                    self.append(
                        "rows_backed_up",
                        image_id=iid,
                        path=str(row_snapshot),
                        sha256=sha256(row_snapshot),
                    )
                else:
                    raise SafetyError("DB row absent without frozen recovery evidence")
                for obj in objects:
                    src = Path(obj["path"])
                    if src.exists():
                        if sha256(src) != obj["sha256"]:
                            raise SafetyError("Source drift before exact deletion")
                        self.append(
                            "file_remove_intent",
                            image_id=iid,
                            path=str(src),
                            sha256=obj["sha256"],
                        )
                        delete_exact(src, obj["sha256"])
                        if src.exists():
                            raise SafetyError("File deletion failed; DB row retained")
                        self.append("file_removed", image_id=iid, path=str(src))
                    elif not any(
                        e["event"] == "file_remove_intent" and e.get("path") == str(src)
                        for e in previous
                    ):
                        raise SafetyError(
                            "Source absent without journaled deletion intent"
                        )
                self.append("db_remove_intent", image_id=iid)
                # DB delete is transactional, includes tombstone and representative
                # repair, and is safe to repeat only with the frozen row identity.
                tombstone = self.db.delete(row)
                self.append("db_removed", image_id=iid, tombstone=tombstone)
                self.db.verify_removed(row)
                if any(Path(o["path"]).exists() for o in objects):
                    raise SafetyError("A manifest-listed file still exists")
                self.append(
                    "verified", image_id=iid, replacement_id=row["replacement_id"]
                )
                previous = self.events()
            expiry = datetime.now(timezone.utc) + timedelta(days=30)
            receipt = {
                "manifest_sha256": self.digest,
                "removed": len(self.entries),
                "verified": True,
                "raw_bytes_removed": sum(r["size"] for r in self.entries),
                "backup_expiry_not_before": expiry.isoformat(),
                "net_free_space_note": "Copies on the same drive defer net reclamation until a separately authorized purge.",
            }
            durable_write(
                self.backup / "receipt.json", json.dumps(receipt, indent=1).encode()
            )
            return receipt
        finally:
            if hasattr(self.db, "abort"):
                self.db.abort()
            release(fd)

    def recover(self):
        self.verify_backup_receipt()
        self.db.assert_quiescent()
        if not self.backup.is_dir():
            raise SafetyError("No recovery checkpoint exists")
        lock = self.backup / "apply.lock"
        fd = acquire(lock)
        try:
            return self._recover()
        finally:
            if hasattr(self.db, "abort"):
                self.db.abort()
            release(fd)

    def _recover(self):
        # DB adapter refuses overwriting independently recreated records and uses
        # the frozen rows to recover cascaded dependencies and only our tombstone.
        previous = self.events(allow_incomplete_tail=True, repair_tail=True)
        recovered = 0
        for row in reversed(self.entries):
            iid = row["image_id"]
            if not any(
                e.get("image_id") == iid and e["event"] == "rows_backed_up"
                for e in previous
            ):
                if any(
                    e.get("image_id") == iid
                    and e["event"] in ("file_remove_intent", "db_remove_intent")
                    for e in previous
                ):
                    raise SafetyError("Deletion intent without recovery rows")
                if any(
                    not Path(o["path"]).is_file() or sha256(o["path"]) != o["sha256"]
                    for o in [row, *row.get("sidecars", [])]
                ):
                    raise SafetyError("Unstarted recovery source changed")
                self.db.check_identity(row)
                continue
            directory = self.backup / str(iid)
            for obj in [row, *row.get("sidecars", [])]:
                src = checked_path(obj["path"], self.roots)
                copy = directory / src.name
                if not copy.is_file() or sha256(copy) != obj["sha256"]:
                    raise SafetyError("Recovery copy missing or corrupt")
                if src.exists() and sha256(src) != obj["sha256"]:
                    raise SafetyError(
                        "Recovery would overwrite different source content"
                    )
            snapshot = directory / "rows.json"
            backed = [
                e
                for e in previous
                if e["event"] == "rows_backed_up" and e.get("image_id") == iid
            ]
            if not backed or sha256(snapshot) != backed[-1]["sha256"]:
                raise SafetyError("Row recovery evidence missing or corrupt")
            for obj in [row, *row.get("sidecars", [])]:
                src = Path(obj["path"])
                if not src.exists():
                    # Stage beside the source: a hard link cannot cross volumes,
                    # and the backup may live on another drive.
                    temporary = src.parent / ("." + src.name + ".neardupe-recovering")
                    if temporary.exists() and sha256(temporary) != obj["sha256"]:
                        temporary.unlink()  # Our own interrupted staging copy.
                    if not temporary.exists():
                        shutil.copy2(directory / src.name, temporary)
                    if sha256(temporary) != obj["sha256"]:
                        raise SafetyError("Incomplete recovery copy")
                    sync_file(temporary)
                    # Atomic, refuses replacement if another writer creates src.
                    os.link(temporary, src)
                    temporary.unlink()
                    if sha256(src) != obj["sha256"]:
                        raise SafetyError("Restored file hash mismatch")
            self.db.restore(row, json.loads(snapshot.read_text(encoding="utf-8")))
            self.db.check_identity(row)
            self.append("recovered", image_id=iid)
            recovered += 1
        return {"recovered": recovered, "manifest_sha256": self.digest}
