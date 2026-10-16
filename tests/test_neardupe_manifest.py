import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys

from scripts.neardupe_maintenance.maintenance import Executor, SafetyError, sha256


class FakeDB:
    def __init__(self):
        self.ids = {1, 2}
        self.fail = False
        self.human_labelled = set()

    def assert_removable(self, row):
        if row["image_id"] in self.human_labelled:
            raise SafetyError("human-labelled frame is protected")

    def identity(self):
        return {"database": "isolated_test"}

    def assert_quiescent(self):
        pass

    def check_identity(self, row):
        if row["image_id"] not in self.ids or row["replacement_id"] not in self.ids:
            raise SafetyError("missing DB identity")

    def snapshot(self, row):
        return {"id": row["image_id"]}

    def exists(self, iid):
        return iid in self.ids

    def delete(self, row):
        if self.fail:
            raise RuntimeError("injected DB failure")
        self.ids.discard(row["image_id"])
        return 10

    def verify_removed(self, row):
        assert row["image_id"] not in self.ids and row["replacement_id"] in self.ids

    def restore(self, row, snapshot):
        self.ids.add(row["image_id"])


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.photos = root / "photos"
        self.photos.mkdir()
        a = self.photos / "a.NEF"
        a.write_bytes(b"raw-a")
        b = self.photos / "b.NEF"
        b.write_bytes(b"raw-b")
        side = self.photos / "a.xmp"
        side.write_bytes(b"xmp-a")
        dump = root / "db.dump"
        dump.write_bytes(b"isolated verified test dump")
        receipt = root / "restore.json"
        receipt.write_text("{}")
        self.row = {
            "image_id": 1,
            "path": str(a),
            "db_path": str(a),
            "size": a.stat().st_size,
            "sha256": sha256(a),
            "replacement_id": 2,
            "replacement_path": str(b),
            "replacement_db_path": str(b),
            "replacement_sha256": sha256(b),
            "judge_keys": ["g1"],
            "audit_receipt": "audited-g1",
            "protected_reasons": [],
            "sidecars": [{"path": str(side), "sha256": sha256(side)}],
        }
        self.manifest = {
            "schema": "neardupe-removal/1",
            "validation_status": "audited",
            "entries": [self.row],
            "database_backup": {
                "isolated_restore_verified": True,
                "source_identity": {"database": "isolated_test"},
                "dump_path": str(dump),
                "dump_sha256": sha256(dump),
                "restore_receipt_path": str(receipt),
                "restore_receipt_sha256": sha256(receipt),
            },
        }
        self.path = root / "manifest.json"
        self.db = FakeDB()
        self.backup = root / "backup"

    def executor(self):
        self.path.write_text(json.dumps(self.manifest))
        return Executor(self.path, self.backup, self.db, [self.photos])

    def test_dry_run_has_no_mutations(self):
        e = self.executor()
        before = {p.name: p.read_bytes() for p in self.photos.iterdir()}
        self.assertEqual(e.dry_run()["mutations"], 0)
        self.assertFalse(self.backup.exists())
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in self.photos.iterdir()}
        )
        self.assertEqual(self.db.ids, {1, 2})

    def test_database_and_disk_must_name_the_same_photo(self):
        self.row["db_path"] = self.row["replacement_path"]
        with self.assertRaises(SafetyError):
            self.executor()
        self.assertTrue(Path(self.row["path"]).exists())
        self.assertEqual(self.db.ids, {1, 2})

    def test_interrupt_before_row_receipt_can_resume_without_deletion(self):
        executor = self.executor()
        append = executor.append

        def interrupted(event, **data):
            if event == "rows_backed_up":
                raise RuntimeError("power loss before row receipt")
            append(event, **data)

        with patch.object(executor, "append", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                executor.apply()
        self.assertTrue(Path(self.row["path"]).exists())
        self.assertIn(1, self.db.ids)
        self.assertTrue(executor.apply(resume=True)["verified"])

    def test_resume_repairs_only_an_incomplete_last_journal_record(self):
        executor = self.executor()
        executor.apply()
        with executor.journal.open("ab") as f:
            f.write(b'{"event":')
        self.assertTrue(executor.apply(resume=True)["verified"])
        for line in executor.journal.read_text(encoding="utf-8").splitlines():
            json.loads(line)

    def test_recovery_refuses_concurrent_executor_lock(self):
        executor = self.executor()
        executor.apply()
        from scripts.neardupe_maintenance.locks import acquire, release

        held = acquire(self.backup / "apply.lock")
        try:
            with self.assertRaises(SafetyError):
                executor.recover()
        finally:
            release(held)

    def test_process_termination_releases_executor_lock(self):
        from scripts.neardupe_maintenance.locks import acquire, release

        self.backup.mkdir()
        lock = self.backup / "apply.lock"
        child = subprocess.Popen(
            [
                getattr(sys, "_base_executable", sys.executable),
                "-c",
                'from scripts.neardupe_maintenance.locks import acquire; import sys,time; acquire(sys.argv[1]); print("locked",flush=True); time.sleep(20)',
                str(lock),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
            with self.assertRaises(SafetyError):
                acquire(lock)
            child.kill()
            child.wait(timeout=10)
            held = acquire(lock)
            release(held)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            child.stdout.close()
            child.stderr.close()

    def test_recovery_skips_unstarted_entries_and_undoes_started_in_reverse(self):
        c = self.photos / "c.NEF"
        c.write_bytes(b"raw-c")
        self.db.ids.add(3)
        second = {
            **self.row,
            "image_id": 3,
            "path": str(c),
            "db_path": str(c),
            "sha256": sha256(c),
            "sidecars": [],
        }
        self.manifest["entries"].append(second)
        executor = self.executor()
        executor.apply()
        order = []
        restore = self.db.restore
        with patch.object(
            self.db,
            "restore",
            side_effect=lambda row, snapshot: (
                order.append(row["image_id"]),
                restore(row, snapshot),
            ),
        ):
            executor.recover()
        self.assertEqual(order, [3, 1])

    def test_apply_resume_and_recovery(self):
        e = self.executor()
        e.apply()
        self.assertFalse(Path(self.row["path"]).exists())
        self.assertFalse(Path(self.row["sidecars"][0]["path"]).exists())
        self.assertEqual(e.apply(resume=True)["removed"], 1)
        self.assertEqual(e.apply()["removed"], 1)
        e.recover()
        self.assertEqual(sha256(self.row["path"]), self.row["sha256"])
        self.assertEqual(self.db.ids, {1, 2})

    def test_backup_failure_keeps_source_and_db(self):
        e = self.executor()
        with patch(
            "scripts.neardupe_maintenance.maintenance.shutil.copy2",
            side_effect=OSError("copy failure"),
        ):
            with self.assertRaises(OSError):
                e.apply()
        self.assertTrue(Path(self.row["path"]).exists())
        self.assertEqual(self.db.ids, {1, 2})

    def test_db_failure_can_resume(self):
        e = self.executor()
        self.db.fail = True
        with self.assertRaises(RuntimeError):
            e.apply()
        self.assertFalse(Path(self.row["path"]).exists())
        self.assertEqual(self.db.ids, {1, 2})
        self.db.fail = False
        e.apply(resume=True)
        self.assertEqual(self.db.ids, {2})

    def test_file_deletion_failure_retains_db(self):
        e = self.executor()
        with patch(
            "scripts.neardupe_maintenance.maintenance.delete_exact",
            side_effect=OSError("unlink failure"),
        ):
            with self.assertRaises(OSError):
                e.apply()
        self.assertEqual(self.db.ids, {1, 2})
        self.assertTrue(Path(self.row["path"]).exists())

    def test_unverified_dump_protects_everything(self):
        self.manifest["database_backup"]["isolated_restore_verified"] = False
        with self.assertRaises(SafetyError):
            self.executor().apply()
        self.assertTrue(Path(self.row["path"]).exists())

    def test_restore_receipt_cannot_only_assert_success(self):
        self.manifest["database_backup"]["restore_receipt_sha256"] = "0" * 64
        with self.assertRaises(SafetyError):
            self.executor().apply()
        self.assertTrue(Path(self.row["path"]).exists())

    def test_protected_frame_and_replacement_cycle_rejected(self):
        self.row["protected_reasons"] = ["exported"]
        with self.assertRaises(SafetyError):
            self.executor()
        self.row["protected_reasons"] = []
        self.row["replacement_id"] = 1
        with self.assertRaises(SafetyError):
            self.executor()

    def test_human_labelled_frame_is_protected_before_any_mutation(self):
        self.db.human_labelled.add(1)
        e = self.executor()
        with self.assertRaises(SafetyError):
            e.dry_run()
        with self.assertRaises(SafetyError):
            e.apply()
        self.assertEqual(sha256(self.row["path"]), self.row["sha256"])
        self.assertTrue(Path(self.row["sidecars"][0]["path"]).exists())
        self.assertEqual(self.db.ids, {1, 2})

    def test_recovery_link_stays_on_the_source_volume(self):
        e = self.executor()
        e.apply()
        real_link = os.link

        def same_volume_link(src, dst):
            # Hard links cannot cross volumes; model the backup as another drive.
            if Path(src).parent != Path(dst).parent:
                raise OSError(
                    17, "The system cannot move the file to a different disk drive"
                )
            return real_link(src, dst)

        with patch(
            "scripts.neardupe_maintenance.maintenance.os.link", same_volume_link
        ):
            e.recover()
        self.assertEqual(sha256(self.row["path"]), self.row["sha256"])
        self.assertEqual(
            sha256(self.row["sidecars"][0]["path"]), self.row["sidecars"][0]["sha256"]
        )
        self.assertEqual(
            sorted(p.name for p in self.photos.iterdir()), ["a.NEF", "a.xmp", "b.NEF"]
        )

    def test_duplicate_filename_in_another_folder_does_not_match(self):
        outside = Path(self.tmp.name) / "other"
        outside.mkdir()
        p = outside / "a.NEF"
        p.write_bytes(b"raw-a")
        self.row["path"] = str(p)
        with self.assertRaises(SafetyError):
            self.executor()


if __name__ == "__main__":
    unittest.main()
