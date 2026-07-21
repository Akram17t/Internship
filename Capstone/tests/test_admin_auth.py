from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.main import app  # noqa: E402


class AdminAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name) / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.old_cache_dir = os.environ.get("CONVERSATION_CACHE_DIR")
        os.environ["CONVERSATION_CACHE_DIR"] = str(self.cache_dir)

    def tearDown(self) -> None:
        if self.old_cache_dir is None:
            os.environ.pop("CONVERSATION_CACHE_DIR", None)
        else:
            os.environ["CONVERSATION_CACHE_DIR"] = self.old_cache_dir
        self.temp_dir.cleanup()

    def write_admin_config(self, payload: dict[str, object]) -> None:
        (self.cache_dir / "admin.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_legacy_admin_json_migrates_and_login_still_works(self) -> None:
        self.write_admin_config(
            {
                "email": "Owner@Example.com",
                "password": "owner-pass",
                "name": "Owner",
                "session_secret": "test-secret",
            }
        )

        response = self.client.post(
            "/api/admin/login",
            json={"email": "owner@example.com", "password": "owner-pass"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Owner")
        stored = json.loads((self.cache_dir / "admin.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["admins"][0]["email"], "owner@example.com")
        self.assertNotIn("email", stored)
        self.assertNotIn("password", stored)

    def test_login_accepts_any_configured_admin(self) -> None:
        self.write_admin_config(
            {
                "admins": [
                    {"email": "owner@example.com", "password": "owner-pass", "name": "Owner"},
                    {"email": "hr@example.com", "password": "hr-pass", "name": "HR Admin"},
                ],
                "session_secret": "test-secret",
            }
        )

        response = self.client.post(
            "/api/admin/login",
            json={"email": "hr@example.com", "password": "hr-pass"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "hr@example.com")
        self.assertEqual(response.json()["name"], "HR Admin")

    def test_logged_in_admin_can_create_new_admin(self) -> None:
        self.write_admin_config(
            {
                "admins": [
                    {"email": "owner@example.com", "password": "owner-pass", "name": "Owner"},
                ],
                "session_secret": "test-secret",
            }
        )
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
        login_new_admin = self.client.post(
            "/api/admin/login",
            json={"email": "hr@example.com", "password": "hr-pass"},
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json(), {"email": "hr@example.com", "name": "HR Admin"})
        self.assertEqual(login_new_admin.status_code, 200)
        self.assertEqual(login_new_admin.json()["name"], "HR Admin")

    def test_create_admin_rejects_duplicate_email(self) -> None:
        self.write_admin_config(
            {
                "admins": [
                    {"email": "owner@example.com", "password": "owner-pass", "name": "Owner"},
                ],
                "session_secret": "test-secret",
            }
        )
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
