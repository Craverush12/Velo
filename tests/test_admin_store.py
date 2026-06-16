import tempfile
import unittest
from pathlib import Path

from core import admin_auth
from storage.admin_store import AdminStore


class AdminStoreTests(unittest.TestCase):
    def test_local_store_bootstraps_admin_and_never_returns_password_hash_in_public_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AdminStore.local(Path(tmp))

            created = store.ensure_bootstrap_admin("owner@example.com", "change-me-now")
            created_again = store.ensure_bootstrap_admin("other@example.com", "ignored")
            admin = store.get_admin_by_email("owner@example.com", include_deleted=False)
            public_admin = store.public_admin(admin)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(admin["role"], "super_admin")
        self.assertTrue(admin_auth.verify_password("change-me-now", admin["password_hash"]))
        self.assertNotIn("password_hash", public_admin)

    def test_managed_entities_support_pagination_filters_and_soft_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AdminStore.local(Path(tmp))
            first = store.create_managed_entity(
                entity_type="announcements",
                slug="launch",
                title="Launch",
                status="published",
                payload={"body": "Live"},
                actor_id="admin-1",
            )
            store.create_managed_entity(
                entity_type="announcements",
                slug="draft",
                title="Draft",
                status="draft",
                payload={"body": "Soon"},
                actor_id="admin-1",
            )
            store.delete_managed_entity("announcements", first["id"], actor_id="admin-1")
            visible = store.list_managed_entities("announcements", include_deleted=False)
            all_rows = store.list_managed_entities("announcements", include_deleted=True)

        self.assertEqual(visible["total"], 1)
        self.assertEqual(visible["items"][0]["slug"], "draft")
        self.assertEqual(all_rows["total"], 2)

    def test_audit_logs_record_before_and_after_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AdminStore.local(Path(tmp))
            store.record_audit(
                actor={"id": "admin-1", "email": "owner@example.com"},
                action="entity.update",
                entity_type="faqs",
                entity_id="faq-1",
                before={"title": "Old"},
                after={"title": "New"},
                ip_address="127.0.0.1",
                user_agent="tests",
            )
            logs = store.list_audit_logs()

        self.assertEqual(logs["total"], 1)
        self.assertEqual(logs["items"][0]["before"]["title"], "Old")
        self.assertEqual(logs["items"][0]["after"]["title"], "New")

    def test_sqlalchemy_store_persists_admin_entities_and_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_url = f"sqlite+pysqlite:///{Path(tmp) / 'admin.db'}"
            store = AdminStore.from_database_url(database_url)
            try:
                store.ensure_bootstrap_admin("owner@example.com", "change-me-now")
                admin = store.get_admin_by_email("owner@example.com")
                session = store.create_session(
                    admin_user_id=admin["id"],
                    session_hash=admin_auth.hash_token("session-token"),
                    csrf_hash=admin_auth.hash_token("csrf-token"),
                    expires_at=admin_auth.session_expires_at(),
                    ip_address="127.0.0.1",
                    user_agent="tests",
                )
                entity = store.create_managed_entity(
                    entity_type="feature-flags",
                    slug="beta-mode",
                    title="Beta Mode",
                    status="active",
                    payload={"enabled": True},
                    actor_id=admin["id"],
                )
                store.close()

                reopened = AdminStore.from_database_url(database_url)
                try:
                    persisted_admin = reopened.get_admin_by_email("owner@example.com")
                    persisted_session = reopened.get_session_by_hash(admin_auth.hash_token("session-token"))
                    flags = reopened.list_managed_entities("feature-flags")
                finally:
                    reopened.close()
            finally:
                store.close()

        self.assertEqual(persisted_admin["id"], admin["id"])
        self.assertEqual(persisted_session["id"], session["id"])
        self.assertEqual(flags["items"][0]["id"], entity["id"])


if __name__ == "__main__":
    unittest.main()
