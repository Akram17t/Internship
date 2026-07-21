from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.main import app  # noqa: E402
from backend.cache_db import (  # noqa: E402
    add_admin_account,
    get_state_db_path,
    init_state_db,
    list_admin_accounts,
)


class AdminAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.cache_dir = self.root / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.old_env = {
            "APP_STATE_DB": os.environ.get("APP_STATE_DB"),
            "CONVERSATION_CACHE_DIR": os.environ.get("CONVERSATION_CACHE_DIR"),
        }
        os.environ["APP_STATE_DB"] = str(self.root / "app_state.db")
        os.environ["CONVERSATION_CACHE_DIR"] = str(self.cache_dir)

    def tearDown(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def seed_admin(self, *, email: str, password: str, name: str) -> None:
        add_admin_account(email=email, password=password, name=name)

    def test_fresh_database_seeds_default_admin_and_login_works(self) -> None:
        response = self.client.post(
            "/api/admin/login",
            json={"email": "admin@gmail.com", "password": "admin123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "admin")
        stored = list_admin_accounts()
        self.assertEqual(stored[0]["email"], "admin@gmail.com")

    def test_default_admin_seed_does_not_overwrite_existing_admin(self) -> None:
        init_state_db()
        with closing(sqlite3.connect(get_state_db_path())) as connection:
            connection.execute(
                """
                UPDATE admin_accounts
                SET password = ?, name = ?
                WHERE email = ?
                """,
                ("custom-pass", "Custom Admin", "admin@gmail.com"),
            )
            connection.commit()

        init_state_db()
        old_password_response = self.client.post(
            "/api/admin/login",
            json={"email": "admin@gmail.com", "password": "admin123"},
        )
        custom_password_response = self.client.post(
            "/api/admin/login",
            json={"email": "admin@gmail.com", "password": "custom-pass"},
        )

        self.assertEqual(old_password_response.status_code, 401)
        self.assertEqual(custom_password_response.status_code, 200)
        self.assertEqual(custom_password_response.json()["name"], "Custom Admin")

    def test_login_accepts_any_configured_admin(self) -> None:
        self.seed_admin(email="owner@example.com", password="owner-pass", name="Owner")
        self.seed_admin(email="hr@example.com", password="hr-pass", name="HR Admin")

        response = self.client.post(
            "/api/admin/login",
            json={"email": "hr@example.com", "password": "hr-pass"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "hr@example.com")
        self.assertEqual(response.json()["name"], "HR Admin")

    def test_logged_in_admin_can_create_new_admin(self) -> None:
        self.seed_admin(email="owner@example.com", password="owner-pass", name="Owner")
        login = self.client.post(
            "/api/admin/login",
            json={"email": "owner@example.com", "password": "owner-pass"},
        )
        token = login.json()["token"]

        create_response = self.client.post(
            "/api/admin/admins",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "HR Admin",
                "email": "hr@example.com",
                "password": "hr-pass",
            },
        )
        new_admin_login_response = self.client.post(
            "/api/admin/login",
            json={"email": "hr@example.com", "password": "hr-pass"},
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json(), {"email": "hr@example.com", "name": "HR Admin"})
        self.assertEqual(new_admin_login_response.status_code, 200)
        self.assertEqual(new_admin_login_response.json()["name"], "HR Admin")

    def test_create_admin_rejects_duplicate_email(self) -> None:
        self.seed_admin(email="owner@example.com", password="owner-pass", name="Owner")
        login = self.client.post(
            "/api/admin/login",
            json={"email": "owner@example.com", "password": "owner-pass"},
        )
        token = login.json()["token"]

        response = self.client.post(
            "/api/admin/admins",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Owner Clone",
                "email": "OWNER@example.com",
                "password": "new-pass",
            },
        )

        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
