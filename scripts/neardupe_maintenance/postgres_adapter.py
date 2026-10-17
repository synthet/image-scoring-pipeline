"""PostgreSQL side of exact-manifest maintenance; schema is discovered, not guessed."""

from __future__ import annotations

from collections import deque
import json

from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

from .maintenance import SafetyError

HUMAN_LABEL_SCHEMAS = ("human_labels",)


class PostgresAdapter:
    def __init__(self, conn):
        self.conn = conn
        self.batch = False
        self.schema = {}
        self.fks = []
        with conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute(
                "SELECT c.table_schema,c.table_name,c.column_name,c.udt_name FROM information_schema.columns c JOIN information_schema.tables t USING(table_schema,table_name) WHERE t.table_type='BASE TABLE' AND c.table_schema NOT IN ('pg_catalog','information_schema')"
            )
            for r in c.fetchall():
                self.schema.setdefault((r["table_schema"], r["table_name"]), {})[
                    r["column_name"]
                ] = r["udt_name"]
            c.execute("""SELECT ns.nspname AS child_schema,cl.relname AS child_table,
                a.attname AS child_column,pns.nspname AS parent_schema,pcl.relname AS parent_table,
                pa.attname AS parent_column,k.confdeltype AS delete_action
                FROM pg_constraint k JOIN pg_class cl ON cl.oid=k.conrelid JOIN pg_namespace ns ON ns.oid=cl.relnamespace
                JOIN pg_class pcl ON pcl.oid=k.confrelid JOIN pg_namespace pns ON pns.oid=pcl.relnamespace
                JOIN pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=k.conkey[1]
                JOIN pg_attribute pa ON pa.attrelid=k.confrelid AND pa.attnum=k.confkey[1]
                WHERE k.contype='f' AND array_length(k.conkey,1)=1""")
            self.fks = [dict(r) for r in c.fetchall()]
        # Human ground truth is never a deletion dependency: labelled frames are
        # protected instead, so these rows are neither deleted nor restored.
        self.label_tables = [
            t
            for t, cols in self.schema.items()
            if "image_id" in cols and t[0] in HUMAN_LABEL_SCHEMAS
        ]
        self.direct_tables = [
            t
            for t, cols in self.schema.items()
            if "image_id" in cols
            and t != ("public", "images")
            and t[0] not in HUMAN_LABEL_SCHEMAS
        ]
        conn.rollback()

    def query(self, text, params=()):
        with self.conn.cursor(cursor_factory=RealDictCursor) as c:
            c.execute(text, params)
            return [dict(r) for r in c.fetchall()]

    def identity(self):
        r = self.query(
            "SELECT current_database() AS database,(SELECT system_identifier::text FROM pg_control_system()) AS system_identifier"
        )[0]
        if not self.batch:
            self.conn.rollback()
        return r

    def assert_quiescent(self):
        active = self.query(
            "SELECT id,status FROM jobs WHERE status IN ('running','pending','queued')"
        )
        if not self.batch:
            self.conn.rollback()
        if active:
            raise SafetyError("Mutation-capable jobs are active")

    def begin_batch(self, row):
        self.conn.rollback()
        self.batch = True
        with self.conn.cursor() as c:
            c.execute("SET LOCAL lock_timeout='10s'")
            c.execute("SELECT pg_advisory_xact_lock(20261012,1)")
            # Prevent job enqueue/start during filesystem operations in this batch.
            c.execute("LOCK TABLE jobs IN SHARE MODE")
            c.execute(
                "SELECT id FROM images WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
                ([row["image_id"], row["replacement_id"]],),
            )
            c.execute(
                "SELECT id FROM images WHERE stack_id=(SELECT stack_id FROM images WHERE id=%s) ORDER BY id FOR UPDATE",
                (row["image_id"],),
            )
        self.assert_quiescent()
        if self.exists(row["image_id"]):
            self.check_identity(row)
        elif not self._tombstone(row):
            raise SafetyError("Missing image has no matching deletion tombstone")

    def check_identity(self, row):
        found = self.query(
            "SELECT id,file_path,image_uuid FROM images WHERE id=ANY(%s)",
            ([row["image_id"], row["replacement_id"]],),
        )
        byid = {r["id"]: r for r in found}
        original = byid.get(row["image_id"])
        replacement = byid.get(row["replacement_id"])
        if (
            not original
            or not replacement
            or original["file_path"] != row["db_path"]
            or original["image_uuid"] != row["image_uuid"]
            or replacement["file_path"] != row["replacement_db_path"]
        ):
            raise SafetyError(
                "Frozen image ID, UUID or exact database path no longer agrees"
            )
        if not self.batch:
            self.conn.rollback()

    def assert_removable(self, row):
        for table in self.label_tables:
            if self._rows(table, "image_id", [row["image_id"]]):
                if not self.batch:
                    self.conn.rollback()
                raise SafetyError("Human-labelled frame is protected from removal")
        if not self.batch:
            self.conn.rollback()

    def exists(self, iid):
        result = bool(self.query("SELECT id FROM images WHERE id=%s", (iid,)))
        if not self.batch:
            self.conn.rollback()
        return result

    def _rows(self, table, column, values):
        if table not in self.schema or column not in self.schema[table]:
            raise SafetyError("Undeclared database relation")
        q = sql.SQL("SELECT to_jsonb(t) AS row FROM {} t WHERE {}=ANY(%s)").format(
            sql.Identifier(*table), sql.Identifier(column)
        )
        return [r["row"] for r in self.query(q, (values,))]

    def snapshot(self, row):
        if not self.batch:
            raise SafetyError(
                "Recovery rows must be frozen while the batch locks are held"
            )
        image = self._rows(("public", "images"), "id", [row["image_id"]])[0]
        seed = {("public", "images"): [image]}
        for table in self.direct_tables:
            rows = self._rows(table, "image_id", [row["image_id"]])
            if rows:
                seed[table] = rows
        if image.get("stack_id"):
            seed[("public", "stacks")] = self._rows(
                ("public", "stacks"), "id", [image["stack_id"]]
            )
            seed[("public", "sub_stacks")] = self._rows(
                ("public", "sub_stacks"), "stack_id", [image["stack_id"]]
            )
            seed[("public", "agent_cull_review_groups")] = self._rows(
                ("public", "agent_cull_review_groups"), "stack_id", [image["stack_id"]]
            )
        if image.get("folder_id"):
            seed[("public", "stack_cache")] = self._rows(
                ("public", "stack_cache"), "folder_id", [image["folder_id"]]
            )
        queue = deque(seed)
        seen = {
            t: {json.dumps(r, sort_keys=True) for r in rows} for t, rows in seed.items()
        }
        while queue:
            parent = queue.popleft()
            parents = seed[parent]
            for fk in self.fks:
                if (fk["parent_schema"], fk["parent_table"]) != parent or fk[
                    "delete_action"
                ] not in ("c", "n"):
                    continue
                child = (fk["child_schema"], fk["child_table"])
                if child == ("public", "images"):
                    continue  # Surviving members are not deletion dependencies.
                values = list(
                    {
                        r[fk["parent_column"]]
                        for r in parents
                        if r.get(fk["parent_column"]) is not None
                    }
                )
                if not values:
                    continue
                rows = self._rows(child, fk["child_column"], values)
                fresh = [
                    r
                    for r in rows
                    if json.dumps(r, sort_keys=True)
                    not in seen.setdefault(child, set())
                ]
                if fresh:
                    seed.setdefault(child, []).extend(fresh)
                    seen[child].update(json.dumps(r, sort_keys=True) for r in fresh)
                    if fk["delete_action"] == "c":
                        queue.append(child)
        expected = {}
        for table in (("public", "stacks"), ("public", "sub_stacks")):
            membership = "stack_id" if table[1] == "stacks" else "sub_stack_id"
            for representative in seed.get(table, []):
                remaining = self.query(
                    sql.SQL(
                        "SELECT id FROM images WHERE {}=%s AND id<>%s ORDER BY (id=%s) DESC,score_general DESC NULLS LAST,id LIMIT 1"
                    ).format(sql.Identifier(membership)),
                    (representative["id"], row["image_id"], row["replacement_id"]),
                )
                expected[f"{table[0]}.{table[1]}:{representative['id']}"] = (
                    remaining[0]["id"] if remaining else None
                )
        payload = {
            "source_identity": self.identity(),
            "tables": [
                {"schema": t[0], "table": t[1], "rows": rs}
                for t, rs in seed.items()
                if rs
            ],
            "expected_representatives_after_delete": expected,
            "image_id": row["image_id"],
            "replacement_id": row["replacement_id"],
            "preexisting_tombstone_ids": [
                r["id"]
                for r in self.query(
                    "SELECT id FROM deleted_images WHERE original_id=%s AND image_uuid=%s AND original_path=%s",
                    (row["image_id"], row["image_uuid"], row["db_path"]),
                )
            ],
        }
        return payload

    def _tombstone(self, row):
        records = self.query(
            "SELECT id FROM deleted_images WHERE original_id=%s AND image_uuid=%s AND original_path=%s",
            (row["image_id"], row["image_uuid"], row["db_path"]),
        )
        return records[0]["id"] if records else None

    def delete(self, row):
        if not self.batch:
            raise SafetyError("Database removal requires a locked batch")
        try:
            if not self.exists(row["image_id"]):
                tombstone = self._tombstone(row)
                if not tombstone:
                    raise SafetyError("Idempotent delete lacks matching tombstone")
                self.conn.commit()
                self.batch = False
                return tombstone
            self.check_identity(row)
            self.assert_removable(row)
            image = self.query("SELECT * FROM images WHERE id=%s", (row["image_id"],))[
                0
            ]
            with self.conn.cursor() as c:
                c.execute(
                    "INSERT INTO deleted_images(original_id,image_uuid,image_hash,file_name,original_path) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (
                        image["id"],
                        image["image_uuid"],
                        image["image_hash"],
                        image["file_name"],
                        image["file_path"],
                    ),
                )
                tombstone = c.fetchone()[0]
                # Stack review groups and other members' recommendations are kept;
                # the removed image's own recommendations cascade from images.
                # Some deployed score/selection tables have no FK. An exact
                # image_id predicate removes these dependencies as well.
                for table in self.direct_tables:
                    c.execute(
                        sql.SQL("DELETE FROM {} WHERE image_id=%s").format(
                            sql.Identifier(*table)
                        ),
                        (image["id"],),
                    )
                c.execute("DELETE FROM images WHERE id=%s", (image["id"],))
                if c.rowcount != 1:
                    raise SafetyError("Exact image delete did not remove one row")
                if image["stack_id"] is not None:
                    # sub_stacks.best_image_id has no FK: repair it explicitly.
                    c.execute(
                        """UPDATE sub_stacks s SET best_image_id=(SELECT id FROM images i
                        WHERE i.sub_stack_id=s.id ORDER BY (i.id=%s) DESC,score_general DESC NULLS LAST,id LIMIT 1)
                        WHERE s.stack_id=%s AND (s.best_image_id=%s OR s.best_image_id IS NULL)""",
                        (row["replacement_id"], image["stack_id"], image["id"]),
                    )
                    c.execute(
                        "DELETE FROM sub_stacks s WHERE s.stack_id=%s AND NOT EXISTS (SELECT 1 FROM images i WHERE i.sub_stack_id=s.id)",
                        (image["stack_id"],),
                    )
                    c.execute(
                        """UPDATE stacks s SET best_image_id=(SELECT id FROM images i WHERE i.stack_id=s.id
                        ORDER BY (i.id=%s) DESC,score_general DESC NULLS LAST,id LIMIT 1)
                        WHERE s.id=%s AND (s.best_image_id IS NULL OR s.best_image_id=%s)""",
                        (row["replacement_id"], image["stack_id"], image["id"]),
                    )
                    c.execute(
                        "DELETE FROM stacks s WHERE s.id=%s AND NOT EXISTS (SELECT 1 FROM images i WHERE i.stack_id=s.id)",
                        (image["stack_id"],),
                    )
                if image["folder_id"] is not None:
                    c.execute(
                        "DELETE FROM stack_cache WHERE folder_id=%s",
                        (image["folder_id"],),
                    )
            self.conn.commit()
            self.batch = False
            return tombstone
        except Exception:
            self.abort()
            raise

    def verify_removed(self, row):
        if (
            self.exists(row["image_id"])
            or not self.exists(row["replacement_id"])
            or not self._tombstone(row)
        ):
            raise SafetyError("Post-removal identity verification failed")
        for fk in self.fks:
            if (fk["parent_schema"], fk["parent_table"]) == ("public", "images"):
                q = sql.SQL("SELECT count(*) AS n FROM {} WHERE {}=%s").format(
                    sql.Identifier(fk["child_schema"], fk["child_table"]),
                    sql.Identifier(fk["child_column"]),
                )
                if self.query(q, (row["image_id"],))[0]["n"]:
                    raise SafetyError("Orphan image reference after deletion")
        if self.query(
            "SELECT id FROM sub_stacks WHERE best_image_id=%s", (row["image_id"],)
        ):
            raise SafetyError("Dangling sub-stack representative")
        for table in self.direct_tables:
            if self._rows(table, "image_id", [row["image_id"]]):
                raise SafetyError("Non-FK dependent image row remains")
        self.conn.rollback()

    def _insert_rows(self, table, rows, ignore_columns=()):
        columns = self.schema[table]
        primary = self.query(
            """SELECT a.attname AS name FROM pg_index ix
            JOIN pg_attribute a ON a.attrelid=ix.indrelid AND a.attnum=ANY(ix.indkey)
            WHERE ix.indrelid=to_regclass(%s) AND ix.indisprimary""",
            (".".join(table),),
        )
        keys = [r["name"] for r in primary]
        if not keys:
            raise SafetyError("Recovery relation lacks a primary key")
        # Columns an ON DELETE SET NULL constraint may have cleared during removal.
        set_null = {
            fk["child_column"]
            for fk in self.fks
            if (fk["child_schema"], fk["child_table"]) == table
            and fk["delete_action"] == "n"
        }
        for row in rows:
            where = sql.SQL(" AND ").join(
                sql.SQL("{}=%s").format(sql.Identifier(k)) for k in keys
            )
            old = self.query(
                sql.SQL("SELECT to_jsonb(t) AS row FROM {} t WHERE {}").format(
                    sql.Identifier(*table), where
                ),
                tuple(row[k] for k in keys),
            )
            if old:
                compare = {k: v for k, v in row.items() if k not in ignore_columns}
                actual = {
                    k: v for k, v in old[0]["row"].items() if k not in ignore_columns
                }
                changed = {
                    k
                    for k in compare.keys() | actual.keys()
                    if compare.get(k) != actual.get(k)
                }
                if any(k not in set_null or actual.get(k) is not None for k in changed):
                    raise SafetyError(
                        "Recovery would overwrite an independently changed database row"
                    )
                if changed:
                    names = sorted(changed)
                    with self.conn.cursor() as c:
                        c.execute(
                            sql.SQL("UPDATE {} SET {} WHERE {}").format(
                                sql.Identifier(*table),
                                sql.SQL(",").join(
                                    sql.SQL("{}=%s").format(sql.Identifier(k))
                                    for k in names
                                ),
                                where,
                            ),
                            tuple(row[k] for k in names) + tuple(row[k] for k in keys),
                        )
                continue
            names = list(row)
            values = [
                Json(row[k]) if columns[k] in ("json", "jsonb") else row[k]
                for k in names
            ]
            q = sql.SQL(
                "INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE VALUES ({})"
            ).format(
                sql.Identifier(*table),
                sql.SQL(",").join(map(sql.Identifier, names)),
                sql.SQL(",").join(sql.Placeholder() for _ in names),
            )
            with self.conn.cursor() as c:
                c.execute(q, values)

    def restore(self, row, snapshot):
        if snapshot["source_identity"] != self.identity():
            raise SafetyError("Row recovery targets a different database")
        try:
            self.begin_batch(row)
            tables = {(r["schema"], r["table"]): r["rows"] for r in snapshot["tables"]}
            # Break the representative/member FK cycle while restoring roots.
            for table in (("public", "stacks"), ("public", "sub_stacks")):
                if table in tables:
                    for old in tables[table]:
                        actual = self._rows(table, "id", [old["id"]])
                        expected = snapshot[
                            "expected_representatives_after_delete"
                        ].get(f"{table[0]}.{table[1]}:{old['id']}")
                        if actual and actual[0].get("best_image_id") not in (
                            old.get("best_image_id"),
                            expected,
                        ):
                            raise SafetyError(
                                "Representative changed independently after removal"
                            )
                    adjusted = [{**r, "best_image_id": None} for r in tables[table]]
                    self._insert_rows(table, adjusted, ("best_image_id",))
            self._insert_rows(("public", "images"), tables.pop(("public", "images")))
            pending = {
                t: rs
                for t, rs in tables.items()
                if t not in (("public", "stacks"), ("public", "sub_stacks"))
            }
            # Snapshot insertion order is breadth-first parent-before-child.
            while pending:
                progress = False
                for table in list(pending):
                    parents = {
                        (f["parent_schema"], f["parent_table"])
                        for f in self.fks
                        if (f["child_schema"], f["child_table"]) == table
                    }
                    if any(t in pending for t in parents):
                        continue
                    self._insert_rows(table, pending.pop(table))
                    progress = True
                if not progress:
                    raise SafetyError("Unresolved recovery dependency cycle")
            with self.conn.cursor() as c:
                for table in (("public", "stacks"), ("public", "sub_stacks")):
                    for old in tables.get(table, []):
                        if old.get("best_image_id") is not None:
                            c.execute(
                                sql.SQL(
                                    "UPDATE {} SET best_image_id=%s WHERE id=%s"
                                ).format(sql.Identifier(*table)),
                                (old["best_image_id"], old["id"]),
                            )
                c.execute(
                    "DELETE FROM deleted_images WHERE original_id=%s AND image_uuid=%s AND original_path=%s AND NOT (id=ANY(%s))",
                    (
                        row["image_id"],
                        row["image_uuid"],
                        row["db_path"],
                        snapshot["preexisting_tombstone_ids"],
                    ),
                )
            self.conn.commit()
            self.batch = False
        except Exception:
            self.abort()
            raise

    def abort(self):
        self.conn.rollback()
        self.batch = False
