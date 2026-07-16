from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.main import app  # noqa: E402
from backend.api.routes_public import _record_chat_activity  # noqa: E402
from backend.cache_db import (  # noqa: E402
    get_state_db_path,
    init_state_db,
    insert_activity_log,
    list_activity_logs,
)


class AdminLogsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.old_env = {
            "APP_STATE_DB": os.environ.get("APP_STATE_DB"),
            "CONVERSATION_CACHE_DIR": os.environ.get("CONVERSATION_CACHE_DIR"),
        }
        os.environ["APP_STATE_DB"] = str(self.root / "app_state.db")
        os.environ["CONVERSATION_CACHE_DIR"] = str(self.root / "cache")
        (self.root / "cache").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_logs_endpoint_requires_admin(self) -> None:
        response = self.client.get("/api/admin/logs")

        self.assertEqual(response.status_code, 401)

    def test_chat_activity_keeps_full_answer_for_expanded_view(self) -> None:
        answer = "Jawaban lengkap " * 40

        with patch("backend.api.routes_public.insert_activity_log") as insert_log:
            _record_chat_activity(
                status="success",
                conversation_id="conversation-test",
                question="Pertanyaan lengkap",
                answer=answer,
                answer_source="model",
                response_time_seconds=1.25,
            )

        details = insert_log.call_args.kwargs["details"]
        self.assertEqual(details["answer"], answer.strip())
        self.assertLessEqual(len(details["answer_preview"]), 300)

    def test_logs_endpoint_returns_chat_only(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Pertanyaan chat",
            details={"answer_source": "cache"},
        )
        insert_activity_log(
            event_type="document",
            action="insert",
            status="success",
            summary="SOP Test.pdf",
            details={"requires_reindex": True},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get("/api/admin/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["event_type"], "chat")
        self.assertEqual(payload[0]["details"]["answer_source"], "cache")

    def test_logs_endpoint_filters_by_date_range(self) -> None:
        init_state_db()
        today = datetime.now().date()
        old_day = today - timedelta(days=10)
        with closing(sqlite3.connect(get_state_db_path())) as connection:
            connection.execute(
                """
                INSERT INTO activity_logs(
                    event_type, action, status, summary, details_json, created_at
                )
                VALUES ('chat', 'query', 'success', 'old chat', '{}', ?)
                """,
                (datetime.combine(old_day, datetime.min.time()).isoformat(timespec="seconds"),),
            )
            connection.execute(
                """
                INSERT INTO activity_logs(
                    event_type, action, status, summary, details_json, created_at
                )
                VALUES ('chat', 'query', 'success', 'today chat', '{}', ?)
                """,
                (datetime.combine(today, datetime.min.time()).isoformat(timespec="seconds"),),
            )
            connection.commit()

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get(
                f"/api/admin/logs?start_date={today.isoformat()}&end_date={today.isoformat()}"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["summary"], "today chat")

    def test_logs_summary_counts_chat_activity(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Chat 1",
            details={"conversation_id": "conv-a", "answer_source": "model"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Chat 2",
            details={"conversation_id": "conv-a", "answer_source": "fallback"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="error",
            summary="Chat 3",
            details={"conversation_id": "conv-b"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get("/api/admin/logs/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_chat"], 3)
        self.assertEqual(payload["total_sessions"], 2)
        self.assertEqual(payload["average_chat_per_session"], 1.5)
        self.assertEqual(payload["fallback_or_error"], 2)

    def test_document_save_does_not_create_activity_log(self) -> None:
        data_dir = self.root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        with (
            patch.dict(os.environ, {"DATA_DIR": str(data_dir)}),
            patch("backend.api.routes_admin._require_admin", return_value=None),
        ):
            response = self.client.post(
                "/api/admin/documents",
                json={
                    "filename": "SOP Test.txt",
                    "content_base64": "SGVsbG8=",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list_activity_logs(event_type="document"), [])


if __name__ == "__main__":
    unittest.main()
