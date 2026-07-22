from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from backend.api.core import MAX_CONVERSATION_MESSAGES
from backend.api.cache_store import _load_faqs, _save_faqs
from backend.api.models import CitationResponse, FAQItem
from backend.cache_db import (
    append_conversation_turn,
    get_conversation_context,
    get_semantic_cache_entry_by_question,
    get_state_db_path,
    init_state_db,
    insert_activity_log,
    insert_semantic_cache_entry,
    list_faq_items,
    list_activity_log_sessions,
    list_activity_logs,
    load_conversations,
    replace_conversations,
    replace_faq_items,
    state_counts,
    summarize_activity_logs,
)


class CacheDbTests(unittest.TestCase):
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

    def test_migrates_legacy_conversations_json(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        legacy = {
            "conv-1": [
                {"role": "user", "content": "Pertanyaan lama", "created_at": now},
                {"role": "assistant", "content": "Jawaban lama", "created_at": now},
            ]
        }
        (self.root / "cache" / "conversations.json").write_text(
            json.dumps(legacy),
            encoding="utf-8",
        )

        init_state_db()

        conversations = load_conversations()
        self.assertIn("conv-1", conversations)
        self.assertEqual(len(conversations["conv-1"]), 2)

    def test_faq_helpers_store_items_in_state_database(self) -> None:
        faq = FAQItem(
            id="faq-resign",
            question="Bagaimana prosedur resign?",
            answer="Karyawan menyerahkan surat resign ke atasan. [1]",
            suggested_query="Bagaimana prosedur resign?",
            citations=[
                CitationResponse(
                    id=1,
                    source="SOP - Terminasi Hubungan Kerja.pdf",
                    page=3,
                )
            ],
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )

        _save_faqs([faq])

        loaded = _load_faqs()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "faq-resign")
        self.assertEqual(loaded[0].citations[0].source, "SOP - Terminasi Hubungan Kerja.pdf")
        self.assertEqual(state_counts()["faq_items"], 1)

    def test_replace_faq_items_overwrites_database_rows(self) -> None:
        replace_faq_items(
            [
                {
                    "id": "faq-one",
                    "question": "Pertanyaan satu?",
                    "answer": "Jawaban satu. [1]",
                    "suggested_query": "Pertanyaan satu?",
                    "citations": [{"id": 1, "source": "SOP A.pdf"}],
                }
            ]
        )
        replace_faq_items(
            [
                {
                    "id": "faq-two",
                    "question": "Pertanyaan dua?",
                    "answer": "Jawaban dua. [1]",
                    "suggested_query": "Pertanyaan dua?",
                    "citations": [{"id": 1, "source": "SOP B.pdf"}],
                }
            ]
        )

        items = list_faq_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "faq-two")

    def test_semantic_cache_exact_lookup_ignores_case_and_punctuation(self) -> None:
        insert_semantic_cache_entry(
            entry_id="entry-hris",
            question="HRIS tuh apa sih",
            answer="HRIS adalah sistem informasi SDM. [1]",
            citations=[{"id": 1, "source": "SOP Test.pdf", "page": 1}],
            selected_forms=[],
            active_index="indexes/current",
            model_name="openai/gpt-oss-20b",
            embed_model_name="Qwen/Qwen3-Embedding-8B",
        )

        entry = get_semantic_cache_entry_by_question(
            "hris TUH apa sih???",
            active_index="indexes/current",
            model_name="openai/gpt-oss-20b",
            embed_model_name="Qwen/Qwen3-Embedding-8B",
        )

        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "entry-hris")

    def test_append_turn_and_context_uses_latest_messages(self) -> None:
        conversation_id = "conv-context"
        for index in range(8):
            append_conversation_turn(
                conversation_id,
                f"Pertanyaan {index}",
                f"Jawaban {index}",
            )

        context = get_conversation_context(conversation_id)

        self.assertNotIn("Pertanyaan 0", context)
        self.assertIn("Pertanyaan 3", context)
        self.assertIn("Jawaban 7", context)
        self.assertLessEqual(
            len([line for line in context.splitlines() if line.strip()]),
            MAX_CONVERSATION_MESSAGES,
        )

    def test_expired_conversations_are_cleaned_up(self) -> None:
        old_timestamp = (datetime.now() - timedelta(days=3)).isoformat(timespec="seconds")
        replace_conversations(
            {
                "expired": [
                    {"role": "user", "content": "lama", "created_at": old_timestamp},
                    {"role": "assistant", "content": "lama juga", "created_at": old_timestamp},
                ]
            }
        )

        self.assertEqual(load_conversations(), {})

    def test_prunes_to_max_conversations(self) -> None:
        base_time = datetime.now() - timedelta(minutes=4)
        conversations = {
            f"conv-{index}": [
                {
                    "role": "user",
                    "content": f"question {index}",
                    "created_at": (base_time + timedelta(minutes=index)).isoformat(timespec="seconds"),
                }
            ]
            for index in range(4)
        }

        with patch("backend.cache_db.MAX_CONVERSATIONS", 2):
            replace_conversations(conversations)
            stored = load_conversations()

        self.assertEqual(set(stored), {"conv-2", "conv-3"})

    def test_activity_log_insert_and_filter(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Apa itu HRIS?",
            details={"answer_source": "model"},
        )
        insert_activity_log(
            event_type="document",
            action="insert",
            status="success",
            summary="SOP Test.pdf",
            details={"requires_reindex": True},
        )

        all_logs = list_activity_logs()
        chat_logs = list_activity_logs(event_type="chat")
        document_logs = list_activity_logs(event_type="document")

        self.assertEqual(len(all_logs), 2)
        self.assertEqual(len(chat_logs), 1)
        self.assertEqual(chat_logs[0]["event_type"], "chat")
        self.assertEqual(chat_logs[0]["details"]["answer_source"], "model")
        self.assertEqual(len(document_logs), 1)
        self.assertTrue(document_logs[0]["details"]["requires_reindex"])

    def test_activity_logs_filter_by_conversation_id(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Chat A",
            details={"conversation_id": "conv-a", "answer_source": "model"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Chat B",
            details={"conversation_id": "conv-b", "answer_source": "model"},
        )

        logs = list_activity_logs(event_type="chat", conversation_id="conv-a")
        summary = summarize_activity_logs(event_type="chat", conversation_id="conv-a")

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["summary"], "Chat A")
        self.assertEqual(summary["total_chat"], 1)
        self.assertEqual(summary["total_sessions"], 1)
        self.assertEqual(summary["average_chat_per_session"], 1)

    def test_activity_log_sessions_group_by_conversation_id(self) -> None:
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="Old question",
            details={
                "conversation_id": "conv-a",
                "question": "Old question",
                "answer_source": "model",
            },
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="error",
            summary="Latest question",
            details={"conversation_id": "conv-a", "question": "Latest question"},
        )
        insert_activity_log(
            event_type="chat",
            action="query",
            status="success",
            summary="No session",
            details={"answer_source": "model"},
        )

        sessions = list_activity_log_sessions(event_type="chat")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["conversation_id"], "conv-a")
        self.assertEqual(sessions[0]["question_count"], 2)
        self.assertEqual(sessions[0]["fallback_or_error"], 1)
        self.assertEqual(sessions[0]["first_question"], "Old question")
        self.assertEqual(sessions[0]["latest_question"], "Latest question")
        self.assertEqual(sessions[0]["latest_status"], "error")

    def test_activity_log_retention_removes_old_rows(self) -> None:
        init_state_db()
        old_timestamp = (datetime.now() - timedelta(days=31)).isoformat(timespec="seconds")
        fresh_timestamp = datetime.now().isoformat(timespec="seconds")
        with closing(sqlite3.connect(get_state_db_path())) as connection:
            connection.execute(
                """
                INSERT INTO activity_logs(
                    event_type, action, status, summary, details_json, created_at
                )
                VALUES ('chat', 'query', 'success', 'old', '{}', ?)
                """,
                (old_timestamp,),
            )
            connection.execute(
                """
                INSERT INTO activity_logs(
                    event_type, action, status, summary, details_json, created_at
                )
                VALUES ('chat', 'query', 'success', 'fresh', '{}', ?)
                """,
                (fresh_timestamp,),
            )
            connection.commit()

        logs = list_activity_logs()

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["summary"], "fresh")

    def test_activity_log_reads_and_writes_are_thread_safe(self) -> None:
        errors: list[BaseException] = []

        def insert_logs() -> None:
            try:
                for index in range(20):
                    insert_activity_log(
                        event_type="chat",
                        action="query",
                        status="success",
                        summary=f"chat {index}",
                        details={"conversation_id": f"conv-{index % 3}"},
                    )
            except BaseException as error:  # pragma: no cover - reported below
                errors.append(error)

        def read_logs() -> None:
            try:
                for _ in range(20):
                    list_activity_logs(event_type="chat")
                    summarize_activity_logs(event_type="chat")
            except BaseException as error:  # pragma: no cover - reported below
                errors.append(error)

        threads = [
            threading.Thread(target=insert_logs),
            threading.Thread(target=read_logs),
            threading.Thread(target=read_logs),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(list_activity_logs(event_type="chat")), 20)


if __name__ == "__main__":
    unittest.main()
