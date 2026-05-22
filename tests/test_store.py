import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import store
from storage import db


class StoreTests(unittest.TestCase):
    def test_rejects_unsafe_user_id(self):
        with self.assertRaises(ValueError):
            store.get_user_context("../escape")

    def test_save_uses_configured_storage_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "_STORAGE_PATH", Path(tmp).resolve()):
                store.save_user_context("demo-user", {"user_id": "demo-user", "preferences": {}})
                self.assertTrue((Path(tmp) / "user_demo-user.json").exists())
                self.assertFalse((Path(tmp) / "user_demo-user.json.tmp").exists())

    def test_storage_healthcheck_verifies_writable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "_STORAGE_PATH", Path(tmp).resolve()):
                result = store.storage_healthcheck()

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "local")

    def test_database_backend_persists_context_through_existing_store_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_url = f"sqlite+pysqlite:///{Path(tmp) / 'thinkvelocity.db'}"
            backend = db.DatabaseStorage(database_url)
            try:
                with patch.object(store, "_BACKEND", "postgresql"):
                    with patch.object(store, "_DB_STORAGE", backend):
                        context = store.reset_user_context("db-user")
                        context["preferences"]["tone"] = "direct"
                        store.save_user_context("db-user", context)

                        reloaded = store.get_user_context("db-user")
                        health = store.storage_healthcheck()
            finally:
                backend.close()

        self.assertEqual(reloaded["user_id"], "db-user")
        self.assertEqual(reloaded["preferences"]["tone"], "direct")
        self.assertTrue(health["ok"])
        self.assertEqual(health["backend"], "postgresql")

    def test_database_backend_reuses_json_defaults_for_new_users(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_url = f"sqlite+pysqlite:///{Path(tmp) / 'thinkvelocity.db'}"
            backend = db.DatabaseStorage(database_url)
            try:
                with patch.object(store, "_BACKEND", "postgresql"):
                    with patch.object(store, "_DB_STORAGE", backend):
                        context = store.get_user_context("new-db-user")
            finally:
                backend.close()

        self.assertEqual(context["user_id"], "new-db-user")
        self.assertEqual(context["preferences"]["output_style"], "balanced")
        self.assertEqual(context["recent_context"], [])


if __name__ == "__main__":
    unittest.main()
