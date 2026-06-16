import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.admin import get_admin_store
from main import app
from storage.admin_store import AdminStore


class AdminApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AdminStore.local(Path(self.tmp.name))
        self.store.ensure_bootstrap_admin("owner@example.com", "change-me-now")
        app.dependency_overrides[get_admin_store] = lambda: self.store
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.tmp.cleanup()

    def _login(self, email="owner@example.com", password="change-me-now"):
        response = self.client.post(
            "/admin/api/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def test_admin_routes_require_authenticated_session(self):
        response = self.client.get("/admin/api/dashboard")

        self.assertEqual(response.status_code, 401)

    def test_login_me_and_dashboard_work_for_bootstrap_admin(self):
        self._login()

        me = self.client.get("/admin/api/me")
        dashboard = self.client.get("/admin/api/dashboard")

        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["admin"]["email"], "owner@example.com")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertIn("metrics", dashboard.json())

    def test_mutations_require_csrf_and_write_audit_log(self):
        csrf = self._login()

        missing_csrf = self.client.post(
            "/admin/api/announcements",
            json={"slug": "launch", "title": "Launch", "status": "draft", "payload": {"body": "Soon"}},
        )
        created = self.client.post(
            "/admin/api/announcements",
            headers={"X-CSRF-Token": csrf},
            json={"slug": "launch", "title": "Launch", "status": "draft", "payload": {"body": "Soon"}},
        )
        audit = self.client.get("/admin/api/audit-logs")

        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(audit.json()["total"], 1)
        self.assertEqual(audit.json()["items"][0]["action"], "announcements.create")

    def test_read_only_admin_cannot_create_entities(self):
        self.store.create_admin_user(
            email="reader@example.com",
            display_name="Reader",
            password="reader-password",
            role="read_only",
            actor_id="seed",
        )
        csrf = self._login("reader@example.com", "reader-password")

        response = self.client.post(
            "/admin/api/faqs",
            headers={"X-CSRF-Token": csrf},
            json={"slug": "faq", "title": "FAQ", "status": "draft", "payload": {"answer": "No"}},
        )

        self.assertEqual(response.status_code, 403)

    def test_public_health_still_works(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
