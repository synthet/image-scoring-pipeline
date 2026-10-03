"""Folder-cache deletion contracts, using an in-memory transaction double."""

import sys
import types
import unittest
from unittest.mock import patch

import modules
from modules.db_operations import folder_cache


class FakeTransaction:
    def __init__(self, *, occupied=False):
        self.folders = {
            1: {"id": 1, "path": "/photos", "parent_id": None},
            2: {"id": 2, "path": "/photos/day", "parent_id": 1},
        }
        self.image_folder_ids = {2} if occupied else set()
        self.cluster_paths = {"/photos", "/photos/day"}
        self.statements = []

    def query_one(self, sql, params):
        if "WHERE path = ?" in sql:
            return next(
                (
                    row.copy()
                    for row in self.folders.values()
                    if row["path"] == params[0]
                ),
                None,
            )
        if "SELECT path FROM folders WHERE id = ?" in sql:
            row = self.folders.get(params[0])
            return {"path": row["path"]} if row else None
        if "COUNT(*) AS c FROM images" in sql:
            return {"c": len(self.image_folder_ids.intersection(params))}
        raise AssertionError(sql)

    def query(self, sql, params):
        if "SELECT id, path FROM folders WHERE id IN" in sql:
            return [row.copy() for fid, row in self.folders.items() if fid in params]
        if "SELECT id FROM folders WHERE parent_id IN" in sql:
            return [
                {"id": row["id"]}
                for row in self.folders.values()
                if row["parent_id"] in params
            ]
        if "SELECT id FROM folders WHERE parent_id = ?" in sql:
            return [
                {"id": row["id"]}
                for row in self.folders.values()
                if row["parent_id"] == params[0]
            ]
        raise AssertionError(sql)

    def execute(self, sql, params):
        self.statements.append((sql, params))
        if sql.startswith("UPDATE images SET folder_id = NULL"):
            self.image_folder_ids.difference_update(params)
        elif sql.startswith("DELETE FROM cluster_progress"):
            self.cluster_paths.difference_update(params)
        elif sql == "DELETE FROM folders WHERE id = ?":
            root = params[0]
            to_delete = {root}
            while True:
                children = {
                    row["id"]
                    for row in self.folders.values()
                    if row["parent_id"] in to_delete
                }
                if children <= to_delete:
                    break
                to_delete.update(children)
            for fid in to_delete:
                self.folders.pop(fid, None)
        else:
            raise AssertionError(sql)


class FakeConnector:
    def __init__(self, transaction=None, error=None):
        self.tx = transaction or FakeTransaction()
        self.error = error
        self.in_transaction = False
        self.calls = 0

    def run_transaction(self, callback):
        self.calls += 1
        if self.error:
            raise self.error
        self.in_transaction = True
        try:
            return callback(self.tx)
        finally:
            self.in_transaction = False


class FolderCacheOperationsTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.connector = FakeConnector()
        manager = types.SimpleNamespace(broadcast_threadsafe=self._broadcast)
        events_module = types.ModuleType("modules.events")
        events_module.event_manager = manager
        self.patches = [
            patch.dict(sys.modules, {"modules.events": events_module}),
            patch.object(
                modules,
                "utils",
                types.SimpleNamespace(convert_path_to_wsl=lambda path: "/photos"),
                create=True,
            ),
        ]
        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def _broadcast(self, name, payload):
        self.assertFalse(self.connector.in_transaction)
        self.events.append((name, payload))

    def test_empty_subtree_rejects_invalid_and_missing_paths(self):
        invalid = folder_cache.delete_empty_folder_cache_subtree(
            " ", get_connector=lambda: self.connector
        )
        self.assertEqual(invalid["reason"], "invalid")
        self.assertEqual(self.connector.calls, 0)
        missing = folder_cache.delete_empty_folder_cache_subtree(
            "/missing", get_connector=lambda: self.connector
        )
        self.assertEqual(missing["reason"], "not_found")
        self.assertEqual(self.connector.tx.folders.keys(), {1, 2})
        self.assertEqual(self.events, [])

    def test_empty_subtree_with_indexed_image_is_not_deleted(self):
        self.connector = FakeConnector(FakeTransaction(occupied=True))
        result = folder_cache.delete_empty_folder_cache_subtree(
            "/photos", get_connector=lambda: self.connector
        )
        self.assertEqual(result["reason"], "not_empty")
        self.assertEqual(self.connector.tx.folders.keys(), {1, 2})
        self.assertEqual(self.connector.tx.cluster_paths, {"/photos", "/photos/day"})
        self.assertEqual(self.events, [])

    def test_empty_subtree_deletes_then_broadcasts_all_paths(self):
        result = folder_cache.delete_empty_folder_cache_subtree(
            "/photos", get_connector=lambda: self.connector
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_folders"], 2)
        self.assertEqual(self.connector.tx.folders, {})
        self.assertEqual(self.connector.tx.cluster_paths, set())
        self.assertEqual(
            self.events,
            [
                ("folder_deleted", {"path": "/photos"}),
                ("folder_deleted", {"path": "/photos/day"}),
            ],
        )

    def test_maintenance_delete_clears_image_references(self):
        self.connector = FakeConnector(FakeTransaction(occupied=True))
        result = folder_cache.delete_folder_cache_entry(
            "/photos", get_connector=lambda: self.connector
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_folders"], 2)
        self.assertEqual(self.connector.tx.image_folder_ids, set())
        self.assertEqual(self.connector.tx.folders, {})
        self.assertEqual(len(self.events), 2)

    def test_transaction_failure_returns_error_without_events(self):
        self.connector = FakeConnector(error=RuntimeError("database unavailable"))
        result = folder_cache.delete_empty_folder_cache_subtree(
            "/photos", get_connector=lambda: self.connector
        )
        self.assertEqual(result["reason"], "error")
        self.assertIn("database unavailable", result["message"])
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
