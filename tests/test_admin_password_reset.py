import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.database import reset_user_password, verify_password
from app.main import (
    AdminPasswordResetRequest,
    AdminUsersRequest,
    AuthRegisterRequest,
    admin_reset_password,
    list_users_for_admin,
    register_account,
)


class FakeUsersDatabase:
    def __init__(self):
        self.user = {"username": "Ami", "password_hash": "old-hash"}
        self.selected_row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, params=()):
        if sql.startswith("SELECT username FROM users"):
            self.selected_row = self.user if self.user["username"].lower() == params[0].lower() else None
        elif sql.startswith("UPDATE users SET password_hash"):
            self.user["password_hash"] = params[0]

    def fetchone(self):
        return self.selected_row


class AdminPasswordResetTests(unittest.IsolatedAsyncioTestCase):
    def test_database_reset_stores_a_hash_that_verifies_the_new_password(self):
        database = FakeUsersDatabase()
        with patch("app.database.DatabaseContext", return_value=database):
            was_reset = reset_user_password("ami", "pedantix")

        self.assertTrue(was_reset)
        self.assertNotEqual(database.user["password_hash"], "pedantix")
        self.assertTrue(verify_password("pedantix", database.user["password_hash"]))
        self.assertFalse(verify_password("old-password", database.user["password_hash"]))

    async def test_lists_users_only_for_gwen_with_valid_password(self):
        request = AdminUsersRequest(admin_username="Gwen", admin_password="secret")
        with (
            patch("app.main.authenticate_user", return_value={"status": "ok", "username": "Gwen"}),
            patch("app.main.get_all_usernames", return_value=["Gwen", "Ami"]) as list_users,
        ):
            response = await list_users_for_admin(request)

        self.assertEqual(response, {"users": ["Gwen", "Ami"]})
        list_users.assert_called_once_with()

    async def test_rejects_other_accounts_before_authentication(self):
        request = AdminUsersRequest(admin_username="Ami", admin_password="secret")
        with patch("app.main.authenticate_user") as authenticate:
            with self.assertRaises(HTTPException) as error:
                await list_users_for_admin(request)

        self.assertEqual(error.exception.status_code, 403)
        authenticate.assert_not_called()

    async def test_username_must_match_exact_admin_account_name(self):
        request = AdminUsersRequest(admin_username="gwen", admin_password="secret")
        with patch("app.main.authenticate_user") as authenticate:
            with self.assertRaises(HTTPException) as error:
                await list_users_for_admin(request)

        self.assertEqual(error.exception.status_code, 403)
        authenticate.assert_not_called()

    async def test_reserved_admin_name_cannot_be_registered_by_a_new_user(self):
        request = AuthRegisterRequest(username="Gwen", password="pedantix")
        with (
            patch("app.main.user_exists", return_value=False),
            patch("app.main.create_user") as create_user,
        ):
            with self.assertRaises(HTTPException) as error:
                await register_account(request)

        self.assertEqual(error.exception.status_code, 403)
        create_user.assert_not_called()

    async def test_rejects_gwen_when_password_is_invalid(self):
        request = AdminUsersRequest(admin_username="Gwen", admin_password="wrong")
        with patch("app.main.authenticate_user", return_value={"error": "Mot de passe incorrect."}):
            with self.assertRaises(HTTPException) as error:
                await list_users_for_admin(request)

        self.assertEqual(error.exception.status_code, 403)

    async def test_resets_target_password_after_gwen_authenticates(self):
        request = AdminPasswordResetRequest(
            admin_username="Gwen",
            admin_password="secret",
            target_username="Ami",
            new_password="pedantix",
        )
        with (
            patch("app.main.authenticate_user", return_value={"status": "ok", "username": "Gwen"}),
            patch("app.main.reset_user_password", return_value=True) as reset_password,
        ):
            response = await admin_reset_password(request)

        self.assertEqual(response, {"status": "ok", "username": "Ami"})
        reset_password.assert_called_once_with("Ami", "pedantix")

    async def test_does_not_reset_password_when_gwen_authentication_fails(self):
        request = AdminPasswordResetRequest(
            admin_username="Gwen",
            admin_password="wrong",
            target_username="Ami",
            new_password="pedantix",
        )
        with (
            patch("app.main.authenticate_user", return_value={"error": "Mot de passe incorrect."}),
            patch("app.main.reset_user_password") as reset_password,
        ):
            with self.assertRaises(HTTPException) as error:
                await admin_reset_password(request)

        self.assertEqual(error.exception.status_code, 403)
        reset_password.assert_not_called()

    async def test_rejects_short_new_password(self):
        request = AdminPasswordResetRequest(
            admin_username="Gwen",
            admin_password="secret",
            target_username="Ami",
            new_password="x",
        )
        with (
            patch("app.main.authenticate_user", return_value={"status": "ok", "username": "Gwen"}),
            patch("app.main.reset_user_password") as reset_password,
        ):
            with self.assertRaises(HTTPException) as error:
                await admin_reset_password(request)

        self.assertEqual(error.exception.status_code, 400)
        reset_password.assert_not_called()


if __name__ == "__main__":
    unittest.main()
