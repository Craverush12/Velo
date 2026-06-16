import unittest

from core import admin_auth


class AdminAuthTests(unittest.TestCase):
    def test_password_hash_round_trip_and_rejects_wrong_password(self):
        password_hash = admin_auth.hash_password("correct horse battery staple")

        self.assertNotIn("correct horse", password_hash)
        self.assertTrue(admin_auth.verify_password("correct horse battery staple", password_hash))
        self.assertFalse(admin_auth.verify_password("wrong password", password_hash))

    def test_role_permissions_are_ordered_by_admin_responsibility(self):
        self.assertTrue(admin_auth.role_has_permission("super_admin", "admin_users:manage"))
        self.assertFalse(admin_auth.role_has_permission("admin", "admin_users:manage"))
        self.assertTrue(admin_auth.role_has_permission("admin", "pricing:manage"))
        self.assertTrue(admin_auth.role_has_permission("support_ops", "users:edit"))
        self.assertFalse(admin_auth.role_has_permission("support_ops", "pricing:manage"))
        self.assertTrue(admin_auth.role_has_permission("read_only", "users:view"))
        self.assertFalse(admin_auth.role_has_permission("read_only", "users:edit"))

    def test_session_tokens_are_hashed_before_storage(self):
        token = admin_auth.generate_token()
        token_hash = admin_auth.hash_token(token)

        self.assertNotEqual(token, token_hash)
        self.assertEqual(token_hash, admin_auth.hash_token(token))


if __name__ == "__main__":
    unittest.main()
