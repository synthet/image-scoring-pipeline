import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from scripts.neardupe_maintenance.file_delete import delete_exact
from scripts.neardupe_maintenance.maintenance import SafetyError


class ExactFileDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "frame.NEF"
        self.path.write_bytes(b"original raw content")
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_mismatch_keeps_the_actual_file(self):
        with self.assertRaises(SafetyError):
            delete_exact(self.path, "0" * 64)
        self.assertEqual(self.path.read_bytes(), b"original raw content")

    def test_exact_file_is_deleted(self):
        delete_exact(self.path, self.digest)
        self.assertFalse(self.path.exists())

    @unittest.skipUnless(os.name == "nt", "Windows sharing semantics")
    def test_open_file_is_kept(self):
        with self.path.open("rb"):
            with self.assertRaises(OSError):
                delete_exact(self.path, self.digest)
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
