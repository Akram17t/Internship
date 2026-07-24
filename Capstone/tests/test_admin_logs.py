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

    def test_logs_endpoint_filters_negative_feedback_without_exposing_token(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Feedback chat",
            details={
                "conversation_id": "conv-a",
                "feedback_token": "token-feedback-123456",
                "feedback": {
                    "rating": "thumbs_down",
                    "reason": "Kurang lengkap.",
                },
            },
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Normal chat",
            details={"conversation_id": "conv-a"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get("/api/admin/logs?feedback=negative")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["summary"], "Feedback chat")
        self.assertNotIn("feedback_token", payload[0]["details"])
        self.assertEqual(payload[0]["details"]["feedback"]["rating"], "thumbs_down")

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
        self.assertEqual(payload["negative_feedback"], 0)
        self.assertEqual(payload["negative_feedback_rate"], 0)

    def test_feedback_endpoint_updates_chat_log_and_scores_langfuse(self) -> None:
        log_id = insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Question with bad answer",
            details={
                "conversation_id": "conv-feedback",
                "feedback_token": "token-feedback-123456",
                "trace_id": "0" * 32,
            },
        )

        with patch("backend.api.routes_public.score_user_thumbs_down", return_value=True) as score:
            response = self.client.post(
                "/api/feedback",
                json={
                    "feedback_id": log_id,
                    "feedback_token": "token-feedback-123456",
                    "conversation_id": "conv-feedback",
                    "rating": "thumbs_down",
                    "reason": "Jawabannya kurang lengkap.",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        logs = list_activity_logs(event_type="chat")
        self.assertEqual(len(logs), 1)
        self.assertNotIn("feedback_token", logs[0]["details"])
        feedback = logs[0]["details"]["feedback"]
        self.assertEqual(feedback["rating"], "thumbs_down")
        self.assertEqual(feedback["reason"], "Jawabannya kurang lengkap.")
        score.assert_called_once_with(
            trace_id="0" * 32,
            feedback_id=log_id,
            reason="Jawabannya kurang lengkap.",
            conversation_id="conv-feedback",
        )

    def test_feedback_endpoint_rejects_wrong_token_without_new_log(self) -> None:
        log_id = insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Question",
            details={
                "conversation_id": "conv-feedback",
                "feedback_token": "token-feedback-123456",
            },
        )

        response = self.client.post(
            "/api/feedback",
            json={
                "feedback_id": log_id,
                "feedback_token": "wrong-token-123456",
                "conversation_id": "conv-feedback",
                "rating": "thumbs_down",
                "reason": "Jawaban salah.",
            },
        )

        self.assertEqual(response.status_code, 404)
        logs = list_activity_logs(event_type="chat")
        self.assertEqual(len(logs), 1)
        self.assertNotIn("feedback_token", logs[0]["details"])
        self.assertNotIn("feedback", logs[0]["details"])

    def test_feedback_endpoint_validates_reason_length(self) -> None:
        response = self.client.post(
            "/api/feedback",
            json={
                "feedback_id": 1,
                "feedback_token": "token-feedback-123456",
                "conversation_id": "conv-feedback",
                "rating": "thumbs_down",
                "reason": "bad",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_logs_summary_counts_negative_feedback(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Chat 1",
            details={
                "conversation_id": "conv-a",
                "feedback": {"rating": "thumbs_down", "reason": "Kurang pas."},
            },
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Chat 2",
            details={"conversation_id": "conv-a"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get("/api/admin/logs/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["negative_feedback"], 1)
        self.assertEqual(payload["negative_feedback_rate"], 50)

    def test_logs_endpoint_filters_by_conversation_id(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Conv A question",
            details={"conversation_id": "conv-a", "answer_source": "model"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Conv B question",
            details={"conversation_id": "conv-b", "answer_source": "model"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get("/api/admin/logs?conversation_id=conv-a")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["summary"], "Conv A question")

    def test_logs_summary_filters_by_conversation_id(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Conv A success",
            details={"conversation_id": "conv-a", "answer_source": "model"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Conv A fallback",
            details={"conversation_id": "conv-a", "answer_source": "fallback"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="error",
            summary="Conv B error",
            details={"conversation_id": "conv-b"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get("/api/admin/logs/summary?conversation_id=conv-a")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_chat"], 2)
        self.assertEqual(payload["total_sessions"], 1)
        self.assertEqual(payload["average_chat_per_session"], 2)
        self.assertEqual(payload["fallback_or_error"], 1)

    def test_logs_sessions_endpoint_groups_sessions(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Conv A old",
            details={"conversation_id": "conv-a", "question": "Conv A old"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="error",
            summary="Conv A latest",
            details={"conversation_id": "conv-a", "question": "Conv A latest"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="No session",
            details={"answer_source": "model"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.get("/api/admin/logs/sessions")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["conversation_id"], "conv-a")
        self.assertEqual(payload[0]["question_count"], 2)
        self.assertEqual(payload[0]["fallback_or_error"], 1)
        self.assertEqual(payload[0]["first_question"], "Conv A old")
        self.assertEqual(payload[0]["latest_question"], "Conv A latest")
        self.assertEqual(payload[0]["latest_status"], "error")

    def test_delete_log_endpoint_removes_chat_log(self) -> None:
        log_id = insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Delete me",
            details={"conversation_id": "conv-delete"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.delete(f"/api/admin/logs/{log_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Log deleted.")
        self.assertEqual(list_activity_logs(event_type="chat"), [])

    def test_delete_log_endpoint_returns_404_for_missing_log(self) -> None:
        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.delete("/api/admin/logs/999")

        self.assertEqual(response.status_code, 404)

    def test_delete_log_session_endpoint_removes_all_chat_logs_in_session(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Session question 1",
            details={"conversation_id": "conv-delete"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Session question 2",
            details={"conversation_id": "conv-delete"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Other session",
            details={"conversation_id": "conv-keep"},
        )

        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.delete("/api/admin/logs/sessions/conv-delete")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Session logs deleted.")
        remaining = list_activity_logs(event_type="chat")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["details"]["conversation_id"], "conv-keep")

    def test_delete_log_session_endpoint_returns_404_for_missing_session(self) -> None:
        with patch("backend.api.routes_admin._require_admin", return_value=None):
            response = self.client.delete("/api/admin/logs/sessions/missing")

        self.assertEqual(response.status_code, 404)

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
