from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from backend.api.cache_store import _load_faqs, _save_faqs
from backend.api.core import MAX_CONVERSATION_MESSAGES
from backend.api.models import CitationResponse, FAQItem
from backend.db.engine import get_session
from backend.db.models import ActivityLog
from backend.cache_db import (
    add_admin_by_email,
    append_conversation_turn,
    create_conversation,
    delete_conversation,
    get_conversation_context,
    get_conversation_messages,
    get_conversation_owner,
    get_semantic_cache_entry_by_question,
    get_user_by_email,
    insert_activity_log,
    insert_semantic_cache_entry,
    list_activity_log_sessions,
    list_activity_logs,
    list_conversations_for_user,
    list_faq_items,
    rename_conversation,
    replace_faq_items,
    state_counts,
    summarize_activity_logs,
    touch_conversation,
    upsert_user,
)


def test_faq_helpers_store_items_in_the_database() -> None:
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
    assert len(loaded) == 1
    assert loaded[0].id == "faq-resign"
    assert loaded[0].citations[0].source == "SOP - Terminasi Hubungan Kerja.pdf"
    assert state_counts()["faq_items"] == 1


def test_replace_faq_items_overwrites_existing_rows() -> None:
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
    assert len(items) == 1
    assert items[0]["id"] == "faq-two"


def test_semantic_cache_exact_lookup_ignores_case_and_punctuation() -> None:
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

    assert entry is not None
    assert entry["id"] == "entry-hris"


def test_append_turn_and_context_includes_all_turns_within_limit() -> None:
    conversation_id = "conv-context"
    user = upsert_user(email="context-user@icscompute.com", name="Context User")
    create_conversation(conversation_id, user["id"], title="Context test")
    for index in range(8):
        append_conversation_turn(
            conversation_id,
            f"Pertanyaan {index}",
            f"Jawaban {index}",
        )

    context = get_conversation_context(conversation_id)

    # 8 turns (16 messages) fit comfortably under MAX_CONVERSATION_MESSAGES
    # (20), so nothing should be trimmed from the context window.
    assert "Pertanyaan 0" in context
    assert "Jawaban 7" in context


def test_conversation_context_only_shows_latest_messages_beyond_limit() -> None:
    conversation_id = "conv-context-overflow"
    user = upsert_user(email="context-overflow-user@icscompute.com", name="Overflow User")
    create_conversation(conversation_id, user["id"], title="Overflow test")
    turn_count = MAX_CONVERSATION_MESSAGES  # guarantees more messages than the read window
    for index in range(turn_count):
        append_conversation_turn(
            conversation_id,
            f"Pertanyaan {index}",
            f"Jawaban {index}",
        )

    context = get_conversation_context(conversation_id)

    assert "Pertanyaan 0" not in context
    assert f"Jawaban {turn_count - 1}" in context


def test_conversations_are_scoped_and_ordered_per_user() -> None:
    user_a = upsert_user(email="a@icscompute.com", name="A")
    user_b = upsert_user(email="b@icscompute.com", name="B")

    create_conversation("conv-a1", user_a["id"], title="First chat")
    create_conversation("conv-a2", user_a["id"], title="Second chat")
    create_conversation("conv-b1", user_b["id"], title="B's chat")
    touch_conversation(
        "conv-a1",
        updated_at=(datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds"),
    )

    conversations_a = list_conversations_for_user(user_a["id"])
    conversations_b = list_conversations_for_user(user_b["id"])

    assert [item["id"] for item in conversations_a] == ["conv-a1", "conv-a2"]
    assert len(conversations_b) == 1
    assert get_conversation_owner("conv-a1") == user_a["id"]
    assert get_conversation_owner("missing-conversation") is None

    rename_conversation("conv-a2", "Renamed chat")
    renamed = [item for item in list_conversations_for_user(user_a["id"]) if item["id"] == "conv-a2"]
    assert renamed[0]["title"] == "Renamed chat"

    append_conversation_turn("conv-a2", "Hi", "Hello")
    assert len(get_conversation_messages("conv-a2")) == 2

    delete_conversation("conv-a2")
    assert get_conversation_owner("conv-a2") is None
    assert get_conversation_messages("conv-a2") == []


def test_upsert_user_reflects_admin_promotion() -> None:
    user = upsert_user(email="person@icscompute.com", name="Person")
    assert user["is_admin"] is False

    add_admin_by_email(email="person@icscompute.com", name="Person")
    promoted = upsert_user(email="person@icscompute.com", name="Person")

    assert promoted["is_admin"] is True
    assert get_user_by_email("person@icscompute.com")["is_admin"] is True


def test_activity_log_insert_and_filter() -> None:
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

    assert len(all_logs) == 2
    assert len(chat_logs) == 1
    assert chat_logs[0]["event_type"] == "chat"
    assert chat_logs[0]["details"]["answer_source"] == "model"
    assert len(document_logs) == 1
    assert document_logs[0]["details"]["requires_reindex"] is True


def test_activity_logs_filter_by_conversation_id() -> None:
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

    assert len(logs) == 1
    assert logs[0]["summary"] == "Chat A"
    assert summary["total_chat"] == 1
    assert summary["total_sessions"] == 1
    assert summary["average_chat_per_session"] == 1


def test_activity_log_sessions_group_by_conversation_id() -> None:
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

    assert len(sessions) == 1
    assert sessions[0]["conversation_id"] == "conv-a"
    assert sessions[0]["question_count"] == 2
    assert sessions[0]["fallback_or_error"] == 1
    assert sessions[0]["first_question"] == "Old question"
    assert sessions[0]["latest_question"] == "Latest question"
    assert sessions[0]["latest_status"] == "error"


def test_activity_log_retention_removes_old_rows() -> None:
    old_timestamp = datetime.now(timezone.utc) - timedelta(days=31)
    fresh_timestamp = datetime.now(timezone.utc)
    session = get_session()
    try:
        session.add_all(
            [
                ActivityLog(
                    event_type="chat",
                    action="query",
                    status="success",
                    summary="old",
                    details_json={},
                    created_at=old_timestamp,
                ),
                ActivityLog(
                    event_type="chat",
                    action="query",
                    status="success",
                    summary="fresh",
                    details_json={},
                    created_at=fresh_timestamp,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    logs = list_activity_logs()

    assert len(logs) == 1
    assert logs[0]["summary"] == "fresh"


def test_activity_log_reads_and_writes_are_thread_safe() -> None:
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

    assert errors == []
    assert len(list_activity_logs(event_type="chat")) == 20
