"""Recover's overwrite refusal names the table, key and columns (issue #842)."""

import unittest
from unittest import mock

from scripts.neardupe_maintenance.maintenance import SafetyError
from scripts.neardupe_maintenance.postgres_adapter import PostgresAdapter

TABLE = ("public", "stack_cache")


def adapter_with_live_row(live):
    adapter = object.__new__(PostgresAdapter)
    adapter.schema = {
        TABLE: {"stack_id": "int4", "image_count": "int4", "rep_image_id": "int4"}
    }
    adapter.fks = [
        {
            "child_schema": "public",
            "child_table": "stack_cache",
            "child_column": "rep_image_id",
            "delete_action": "n",
        }
    ]
    adapter.conn = mock.MagicMock()
    adapter.query = mock.Mock(side_effect=[[{"name": "stack_id"}], [{"row": live}]])
    return adapter


class RecoverRefusalTests(unittest.TestCase):
    def test_refusal_names_table_key_and_changed_columns(self):
        frozen = {"stack_id": 7, "image_count": 3, "rep_image_id": 50645}
        live = {"stack_id": 7, "image_count": 2, "rep_image_id": 50644}
        adapter = adapter_with_live_row(live)
        with self.assertRaises(SafetyError) as caught:
            adapter._insert_rows(TABLE, [frozen])
        message = str(caught.exception)
        self.assertIn("independently changed database row", message)
        self.assertIn("public.stack_cache (stack_id=7)", message)
        self.assertIn("columns image_count, rep_image_id", message)
        self.assertNotIn("50644", message)
        adapter.conn.cursor.assert_not_called()

    def test_column_cleared_by_set_null_is_still_restored(self):
        frozen = {"stack_id": 7, "image_count": 3, "rep_image_id": 50645}
        live = {"stack_id": 7, "image_count": 3, "rep_image_id": None}
        adapter = adapter_with_live_row(live)
        adapter._insert_rows(TABLE, [frozen])
        cursor = adapter.conn.cursor.return_value.__enter__.return_value
        cursor.execute.assert_called_once()
        self.assertEqual(cursor.execute.call_args.args[1], (50645, 7))


if __name__ == "__main__":
    unittest.main()
