"""Real PostgreSQL integration tests run ONLY in the verified isolated restore."""

import os
import unittest
import uuid
from psycopg2 import sql

from scripts.neardupe_maintenance.maintenance import SafetyError
from scripts.neardupe_maintenance.postgres_adapter import PostgresAdapter


class PostgresMaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = os.environ.get("NEARDUPE_TEST_DB", "")
        if not name.startswith("neardupe_restore_"):
            raise unittest.SkipTest("Explicit isolated restore database required")
        import psycopg2
        from modules.db_postgres import get_pg_config

        cfg = get_pg_config()
        cfg["dbname"] = name
        cls.conn = psycopg2.connect(**cfg)
        with cls.conn.cursor() as c:
            c.execute("SELECT current_database()")
            if c.fetchone()[0] != name:
                raise RuntimeError("Refuse integration tests against wrong database")
        cls.conn.rollback()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.conn.rollback()
        self.token = uuid.uuid4().hex
        with self.conn.cursor() as c:
            c.execute(
                "INSERT INTO stacks(name) VALUES (%s) RETURNING id",
                ("neardupe-test-" + self.token,),
            )
            self.stack = c.fetchone()[0]
            self.ids = []
            self.paths = []
            for n in (1, 2):
                path = f"/tmp/neardupe-{self.token}/{n}.NEF"
                c.execute(
                    "INSERT INTO images(file_path,file_name,image_uuid,stack_id,score_general) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (
                        path,
                        f"{n}.NEF",
                        uuid.uuid4().hex,
                        self.stack,
                        0.8 if n == 1 else 0.9,
                    ),
                )
                self.ids.append(c.fetchone()[0])
                self.paths.append(path)
            c.execute(
                "UPDATE stacks SET best_image_id=%s WHERE id=%s",
                (self.ids[0], self.stack),
            )
            c.execute(
                "INSERT INTO sub_stacks(stack_id,name,best_image_id) VALUES (%s,%s,%s) RETURNING id",
                (self.stack, "test", self.ids[0]),
            )
            self.sub = c.fetchone()[0]
            c.execute(
                "UPDATE images SET sub_stack_id=%s WHERE id=ANY(%s)",
                (self.sub, self.ids),
            )
            c.execute(
                "INSERT INTO image_exif(image_id,make) VALUES (%s,%s)",
                (self.ids[0], "TEST"),
            )
            c.execute(
                "INSERT INTO image_model_scores(image_id,model_name,raw_score,status,is_shadow) VALUES (%s,%s,%s,%s,%s)",
                (self.ids[0], "neardupe-test-model", 55.0, "success", False),
            )
            c.execute("SELECT image_uuid FROM images WHERE id=%s", (self.ids[0],))
            image_uuid = c.fetchone()[0]
        self.conn.commit()
        self.adapter = PostgresAdapter(self.conn)
        self.row = {
            "image_id": self.ids[0],
            "db_path": self.paths[0],
            "image_uuid": image_uuid,
            "replacement_id": self.ids[1],
            "replacement_db_path": self.paths[1],
        }

    def tearDown(self):
        self.conn.rollback()
        with self.conn.cursor() as c:
            c.execute(
                "DELETE FROM image_model_scores WHERE image_id=ANY(%s)", (self.ids,)
            )
            c.execute("DELETE FROM images WHERE id=ANY(%s)", (self.ids,))
            c.execute("DELETE FROM stacks WHERE id=%s", (self.stack,))
            c.execute(
                "DELETE FROM deleted_images WHERE original_id=ANY(%s)", (self.ids,)
            )
            c.execute("SELECT pg_advisory_unlock_all()")
        self.conn.commit()

    def test_path_identity_is_exact(self):
        wrong = {**self.row, "db_path": "/tmp/other/1.NEF"}
        with self.assertRaises(SafetyError):
            self.adapter.check_identity(wrong)

    def test_delete_repairs_representatives_and_cascades(self):
        self.adapter.begin_batch(self.row)
        snapshot = self.adapter.snapshot(self.row)
        self.adapter.delete(self.row)
        self.adapter.verify_removed(self.row)
        with self.conn.cursor() as c:
            c.execute("SELECT best_image_id FROM stacks WHERE id=%s", (self.stack,))
            self.assertEqual(c.fetchone()[0], self.ids[1])
            c.execute("SELECT best_image_id FROM sub_stacks WHERE id=%s", (self.sub,))
            self.assertEqual(c.fetchone()[0], self.ids[1])
            c.execute(
                "SELECT count(*) FROM image_exif WHERE image_id=%s", (self.ids[0],)
            )
            self.assertEqual(c.fetchone()[0], 0)
            c.execute(
                "SELECT count(*) FROM image_model_scores WHERE image_id=%s",
                (self.ids[0],),
            )
            self.assertEqual(c.fetchone()[0], 0)
        self.conn.rollback()
        self.adapter.restore(self.row, snapshot)
        self.adapter.check_identity(self.row)
        with self.conn.cursor() as c:
            c.execute("SELECT make FROM image_exif WHERE image_id=%s", (self.ids[0],))
            self.assertEqual(c.fetchone()[0], "TEST")
            c.execute(
                "SELECT count(*) FROM deleted_images WHERE original_id=%s",
                (self.ids[0],),
            )
            self.assertEqual(c.fetchone()[0], 0)
            c.execute(
                "SELECT raw_score FROM image_model_scores WHERE image_id=%s",
                (self.ids[0],),
            )
            self.assertEqual(c.fetchone()[0], 55.0)
        self.conn.rollback()

    def test_repeated_db_delete_is_idempotent(self):
        self.adapter.begin_batch(self.row)
        self.adapter.delete(self.row)
        self.adapter.begin_batch(self.row)
        self.adapter.delete(self.row)
        self.adapter.verify_removed(self.row)

    def test_recovery_preserves_preexisting_deletion_blocklist(self):
        with self.conn.cursor() as c:
            c.execute(
                "INSERT INTO deleted_images(original_id,image_uuid,original_path,file_name) VALUES (%s,%s,%s,%s) RETURNING id",
                (
                    self.row["image_id"],
                    self.row["image_uuid"],
                    self.row["db_path"],
                    "1.NEF",
                ),
            )
            prior = c.fetchone()[0]
        self.conn.commit()
        self.adapter.begin_batch(self.row)
        snapshot = self.adapter.snapshot(self.row)
        self.adapter.delete(self.row)
        self.adapter.restore(self.row, snapshot)
        with self.conn.cursor() as c:
            c.execute(
                "SELECT id FROM deleted_images WHERE original_id=%s ORDER BY id",
                (self.row["image_id"],),
            )
            self.assertEqual([r[0] for r in c.fetchall()], [prior])
        self.conn.rollback()

    def test_derived_view_is_not_a_recovery_table(self):
        view = "neardupe_test_view_" + self.token
        with self.conn.cursor() as c:
            c.execute(
                sql.SQL(
                    "CREATE VIEW {} AS SELECT image_id,raw_score FROM image_model_scores"
                ).format(sql.Identifier(view))
            )
        self.conn.commit()
        try:
            adapter = PostgresAdapter(self.conn)
            self.assertNotIn(("public", view), adapter.direct_tables)
        finally:
            self.conn.rollback()
            with self.conn.cursor() as c:
                c.execute(sql.SQL("DROP VIEW {}").format(sql.Identifier(view)))
            self.conn.commit()


if __name__ == "__main__":
    unittest.main()
