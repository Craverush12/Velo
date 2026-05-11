import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import store


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


if __name__ == "__main__":
    unittest.main()
