from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.api.core import (
    CONVERSATION_TTL,
    MAX_CONVERSATION_CONTEXT_CHARS,
    MAX_CONVERSATION_MESSAGES,
    MAX_CONVERSATIONS,
    ROOT_DIR,
)
from backend.settings import get_env, load_capstone_env

load_capstone_env()

SCHEMA_VERSION = "2"
MIGRATION_KEY = "conversations_json_migrated"
ACTIVITY_LOG_RETENTION = timedelta(days=30)
MAX_ACTIVITY_LOG_LIMIT = 250
STATE_DB_LOCK = threading.RLock()


def _resolve_root_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def get_state_db_path() -> Path:
    return _resolve_root_path(get_env("APP_STATE_DB", "backend/cache/app_state.db"))


def get_legacy_conversation_file() -> Path:
    cache_dir = _resolve_root_path(get_env("CONVERSATION_CACHE_DIR", "backend/cache"))
    return cache_dir / "conversations.json"


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_state_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=60000")
    try:
        connection.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError as error:
        if "database is locked" not in str(error).lower():
            raise
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def normalize_semantic_question(question: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", question.casefold())
    return " ".join(normalized.split())


def _init_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_state_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_lookup
            ON conversation_messages (conversation_id, created_at, id);
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_created
            ON conversation_messages (created_at);

        CREATE TABLE IF NOT EXISTS semantic_cache_entries (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            normalized_question TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL,
            citations_json TEXT NOT NULL,
            selected_forms_json TEXT NOT NULL,
            active_index TEXT NOT NULL,
            model_name TEXT NOT NULL,
            embed_model_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0,
            last_hit_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_semantic_cache_metadata
            ON semantic_cache_entries (active_index, model_name, embed_model_name);

        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL CHECK (event_type IN ('chat', 'document')),
            action TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN ('success', 'error')),
            summary TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_activity_logs_lookup
            ON activity_logs (event_type, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_activity_logs_created
            ON activity_logs (created_at DESC, id DESC);
        """
    )
    semantic_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(semantic_cache_entries)")
    }
    if "normalized_question" not in semantic_columns:
        connection.execute(
            "ALTER TABLE semantic_cache_entries "
            "ADD COLUMN normalized_question TEXT NOT NULL DEFAULT ''"
        )
    rows_to_normalize = connection.execute(
        """
        SELECT id, question
        FROM semantic_cache_entries
        WHERE normalized_question = ''
        """
    ).fetchall()
    connection.executemany(
        """
        UPDATE semantic_cache_entries
        SET normalized_question = ?
        WHERE id = ?
        """,
        [
            (normalize_semantic_question(str(row["question"])), str(row["id"]))
            for row in rows_to_normalize
        ],
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_semantic_cache_exact
        ON semantic_cache_entries (
            normalized_question, active_index, model_name, embed_model_name
        )
        """
    )
    connection.execute(
        """
        INSERT INTO app_state_meta(key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (SCHEMA_VERSION,),
    )
    connection.commit()


def _get_meta(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM app_state_meta WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row else None


def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO app_state_meta(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _parse_timestamp(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value).isoformat(timespec="seconds")
    except ValueError:
        return None


def _migrate_legacy_conversations(
    connection: sqlite3.Connection,
    legacy_path: Path | None = None,
) -> int:
    path = legacy_path or get_legacy_conversation_file()
    if not path.exists():
        return 0

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(data, dict):
        return 0

    inserted = 0
    for raw_conversation_id, raw_messages in data.items():
        conversation_id = str(raw_conversation_id).strip()
        if not conversation_id or not isinstance(raw_messages, list):
            continue

        for raw_message in raw_messages:
            if not isinstance(raw_message, dict):
                continue
            role = str(raw_message.get("role") or "").strip()
            content = str(raw_message.get("content") or "").strip()
            created_at = _parse_timestamp(raw_message.get("created_at"))
            if role not in {"user", "assistant"} or not content or created_at is None:
                continue
            connection.execute(
                """
                INSERT INTO conversation_messages(
                    conversation_id, role, content, created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, created_at),
            )
            inserted += 1

    return inserted


def init_state_db(
    *,
    db_path: Path | None = None,
    legacy_conversations_path: Path | None = None,
) -> None:
    with STATE_DB_LOCK:
        with closing(_connect(db_path)) as connection:
            _init_schema(connection)
            if _get_meta(connection, MIGRATION_KEY) != "1":
                _migrate_legacy_conversations(connection, legacy_conversations_path)
                _set_meta(connection, MIGRATION_KEY, "1")
            _cleanup_activity_logs(connection)
            _cleanup_conversations(connection)
            connection.commit()


def _cleanup_conversations(connection: sqlite3.Connection, now: datetime | None = None) -> None:
    cutoff = (now or datetime.now()) - CONVERSATION_TTL
    cutoff_value = cutoff.isoformat(timespec="seconds")

    expired_ids = [
        str(row["conversation_id"])
        for row in connection.execute(
            """
            SELECT conversation_id
            FROM conversation_messages
            GROUP BY conversation_id
            HAVING MAX(created_at) < ?
            """,
            (cutoff_value,),
        )
    ]
    for conversation_id in expired_ids:
        connection.execute(
            "DELETE FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        )

    conversation_ids = [
        str(row["conversation_id"])
        for row in connection.execute(
            """
            SELECT conversation_id
            FROM conversation_messages
            GROUP BY conversation_id
            ORDER BY MAX(created_at) DESC
            """
        )
    ]
    for conversation_id in conversation_ids:
        keep_ids = [
            int(row["id"])
            for row in connection.execute(
                """
                SELECT id
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (conversation_id, MAX_CONVERSATION_MESSAGES),
            )
        ]
        if keep_ids:
            placeholders = ",".join("?" for _ in keep_ids)
            connection.execute(
                f"""
                DELETE FROM conversation_messages
                WHERE conversation_id = ?
                AND id NOT IN ({placeholders})
                """,
                (conversation_id, *keep_ids),
            )

    keep_conversation_ids = set(conversation_ids[:MAX_CONVERSATIONS])
    for conversation_id in conversation_ids[MAX_CONVERSATIONS:]:
        if conversation_id not in keep_conversation_ids:
            connection.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (conversation_id,),
            )


def _cleanup_activity_logs(connection: sqlite3.Connection, now: datetime | None = None) -> None:
    cutoff = (now or datetime.now()) - ACTIVITY_LOG_RETENTION
    connection.execute(
        "DELETE FROM activity_logs WHERE created_at < ?",
        (cutoff.isoformat(timespec="seconds"),),
    )


def get_conversation_context(conversation_id: str) -> str:
    with STATE_DB_LOCK:
        init_state_db()
        with closing(_connect()) as connection:
            _cleanup_conversations(connection)
            rows = list(
                connection.execute(
                    """
                    SELECT role, content
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (conversation_id, MAX_CONVERSATION_MESSAGES),
                )
            )
            connection.commit()

    context_lines: list[str] = []
    for row in reversed(rows):
        role = "User" if row["role"] == "user" else "Assistant"
        content = str(row["content"]).strip()
        if content:
            context_lines.append(f"{role}: {content}")
    return "\n".join(context_lines)[-MAX_CONVERSATION_CONTEXT_CHARS:]


def append_conversation_turn(conversation_id: str, question: str, answer: str) -> None:
    with STATE_DB_LOCK:
        init_state_db()
        now = datetime.now().isoformat(timespec="seconds")
        with closing(_connect()) as connection:
            _cleanup_conversations(connection)
            connection.executemany(
                """
                INSERT INTO conversation_messages(
                    conversation_id, role, content, created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    (conversation_id, "user", question.strip(), now),
                    (conversation_id, "assistant", answer.strip(), now),
                ),
            )
            _cleanup_conversations(connection)
            connection.commit()


def insert_activity_log(
    *,
    event_type: str,
    action: str,
    status: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> int:
    with STATE_DB_LOCK:
        init_state_db()
        now = datetime.now().isoformat(timespec="seconds")
        with closing(_connect()) as connection:
            _cleanup_activity_logs(connection)
            cursor = connection.execute(
                """
                INSERT INTO activity_logs(
                    event_type, action, status, summary, details_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    action.strip(),
                    status,
                    summary.strip(),
                    json.dumps(details or {}, ensure_ascii=False),
                    now,
                ),
            )
            _cleanup_activity_logs(connection)
            connection.commit()
            return int(cursor.lastrowid)


def delete_activity_log(log_id: int, *, event_type: str | None = None) -> bool:
    with STATE_DB_LOCK:
        init_state_db()
        filters = ["id = ?"]
        params: list[object] = [log_id]
        if event_type in {"chat", "document"}:
            filters.append("event_type = ?")
            params.append(event_type)
        with closing(_connect()) as connection:
            cursor = connection.execute(
                f"DELETE FROM activity_logs WHERE {' AND '.join(filters)}",
                params,
            )
            connection.commit()
            return cursor.rowcount > 0


def delete_activity_logs_for_conversation(
    conversation_id: str,
    *,
    event_type: str | None = None,
) -> int:
    selected_conversation_id = conversation_id.strip()
    if not selected_conversation_id:
        return 0
    with STATE_DB_LOCK:
        init_state_db()
        filters: list[str] = []
        params: list[object] = []
        if event_type in {"chat", "document"}:
            filters.append("event_type = ?")
            params.append(event_type)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        with closing(_connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, details_json
                FROM activity_logs
                {where_clause}
                """,
                params,
            ).fetchall()
            delete_ids = [
                int(row["id"])
                for row in rows
                if _activity_log_conversation_id(row) == selected_conversation_id
            ]
            if not delete_ids:
                connection.commit()
                return 0
            placeholders = ",".join("?" for _ in delete_ids)
            cursor = connection.execute(
                f"DELETE FROM activity_logs WHERE id IN ({placeholders})",
                delete_ids,
            )
            connection.commit()
            return int(cursor.rowcount)


def _activity_log_from_row(row: sqlite3.Row) -> dict[str, Any]:
    details = _activity_log_details(row)
    return {
        "id": int(row["id"]),
        "event_type": str(row["event_type"]),
        "action": str(row["action"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "details": details if isinstance(details, dict) else {},
        "created_at": str(row["created_at"]),
    }


def _activity_log_details(row: sqlite3.Row) -> dict[str, Any]:
    try:
        details = json.loads(str(row["details_json"]))
    except json.JSONDecodeError:
        details = {}
    return details if isinstance(details, dict) else {}


def _activity_log_conversation_id(row: sqlite3.Row) -> str:
    return str(_activity_log_details(row).get("conversation_id") or "").strip()


def _activity_log_is_fallback_or_error(row: sqlite3.Row) -> bool:
    details = _activity_log_details(row)
    answer_source = str(details.get("answer_source") or "").strip()
    return row["status"] == "error" or answer_source == "fallback"


def list_activity_logs(
    *,
    event_type: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    conversation_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with STATE_DB_LOCK:
        init_state_db()
        bounded_limit = max(1, min(limit, MAX_ACTIVITY_LOG_LIMIT))
        bounded_offset = max(0, offset)
        selected_conversation_id = str(conversation_id or "").strip()
        filters: list[str] = []
        params: list[object] = []
        if event_type in {"chat", "document"}:
            filters.append("event_type = ?")
            params.append(event_type)
        if start_at:
            filters.append("created_at >= ?")
            params.append(start_at)
        if end_at:
            filters.append("created_at <= ?")
            params.append(end_at)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        with closing(_connect()) as connection:
            _cleanup_activity_logs(connection)
            if selected_conversation_id:
                rows = connection.execute(
                    f"""
                    SELECT *
                    FROM activity_logs
                    {where_clause}
                    ORDER BY created_at DESC, id DESC
                    """,
                    params,
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT *
                    FROM activity_logs
                    {where_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (*params, bounded_limit, bounded_offset),
                ).fetchall()
            connection.commit()
    if selected_conversation_id:
        rows = [
            row
            for row in rows
            if _activity_log_conversation_id(row) == selected_conversation_id
        ][bounded_offset : bounded_offset + bounded_limit]
    return [_activity_log_from_row(row) for row in rows]


def summarize_activity_logs(
    *,
    event_type: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, int | float]:
    with STATE_DB_LOCK:
        init_state_db()
        selected_conversation_id = str(conversation_id or "").strip()
        filters: list[str] = []
        params: list[object] = []
        if event_type in {"chat", "document"}:
            filters.append("event_type = ?")
            params.append(event_type)
        if start_at:
            filters.append("created_at >= ?")
            params.append(start_at)
        if end_at:
            filters.append("created_at <= ?")
            params.append(end_at)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        with closing(_connect()) as connection:
            _cleanup_activity_logs(connection)
            rows = connection.execute(
                f"""
                SELECT status, details_json
                FROM activity_logs
                {where_clause}
                """,
                params,
            ).fetchall()
            connection.commit()
    if selected_conversation_id:
        rows = [
            row
            for row in rows
            if _activity_log_conversation_id(row) == selected_conversation_id
        ]

    sessions: set[str] = set()
    fallback_or_error = 0
    for row in rows:
        row_conversation_id = _activity_log_conversation_id(row)
        if row_conversation_id:
            sessions.add(row_conversation_id)
        if _activity_log_is_fallback_or_error(row):
            fallback_or_error += 1

    total = len(rows)
    session_count = len(sessions)
    average = round(total / session_count, 2) if session_count else 0
    return {
        "total_chat": total,
        "total_sessions": session_count,
        "average_chat_per_session": average,
        "fallback_or_error": fallback_or_error,
    }


def list_activity_log_sessions(
    *,
    event_type: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
) -> list[dict[str, Any]]:
    with STATE_DB_LOCK:
        init_state_db()
        filters: list[str] = []
        params: list[object] = []
        if event_type in {"chat", "document"}:
            filters.append("event_type = ?")
            params.append(event_type)
        if start_at:
            filters.append("created_at >= ?")
            params.append(start_at)
        if end_at:
            filters.append("created_at <= ?")
            params.append(end_at)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        with closing(_connect()) as connection:
            _cleanup_activity_logs(connection)
            rows = connection.execute(
                f"""
                SELECT id, status, summary, details_json, created_at
                FROM activity_logs
                {where_clause}
                ORDER BY created_at ASC, id ASC
                """,
                params,
            ).fetchall()
            connection.commit()

    sessions: dict[str, dict[str, Any]] = {}
    for row in rows:
        details = _activity_log_details(row)
        conversation_id = str(details.get("conversation_id") or "").strip()
        if not conversation_id:
            continue
        created_at = str(row["created_at"])
        row_id = int(row["id"])
        item = sessions.setdefault(
            conversation_id,
            {
                "conversation_id": conversation_id,
                "question_count": 0,
                "fallback_or_error": 0,
                "_first_id": row_id,
                "_last_id": row_id,
                "first_at": created_at,
                "last_at": created_at,
                "first_question": "",
                "latest_question": "",
                "latest_status": "success",
            },
        )
        item["question_count"] += 1
        if _activity_log_is_fallback_or_error(row):
            item["fallback_or_error"] += 1
        question = str(details.get("question") or row["summary"] or "").strip()
        if (created_at, row_id) < (item["first_at"], item["_first_id"]):
            item["_first_id"] = row_id
            item["first_at"] = created_at
            item["first_question"] = question
        elif not item["first_question"]:
            item["first_question"] = question
        if (created_at, row_id) > (item["last_at"], item["_last_id"]):
            item["_last_id"] = row_id
            item["last_at"] = created_at
            item["latest_question"] = question
            item["latest_status"] = str(row["status"])
        elif not item["latest_question"]:
            item["latest_question"] = question
            item["latest_status"] = str(row["status"])

    for item in sessions.values():
        item.pop("_first_id", None)
        item.pop("_last_id", None)

    return sorted(
        sessions.values(),
        key=lambda item: (str(item["last_at"]), str(item["conversation_id"])),
        reverse=True,
    )


def load_conversations() -> dict[str, list[dict[str, object]]]:
    conversations: dict[str, list[dict[str, object]]] = {}
    with STATE_DB_LOCK:
        init_state_db()
        with closing(_connect()) as connection:
            _cleanup_conversations(connection)
            rows = connection.execute(
                """
                SELECT conversation_id, role, content, created_at
                FROM conversation_messages
                ORDER BY conversation_id, created_at, id
                """
            )
            for row in rows:
                conversations.setdefault(str(row["conversation_id"]), []).append(
                    {
                        "role": str(row["role"]),
                        "content": str(row["content"]),
                        "created_at": str(row["created_at"]),
                    }
                )
            connection.commit()
    return conversations


def replace_conversations(conversations: dict[str, list[dict[str, object]]]) -> None:
    with STATE_DB_LOCK:
        init_state_db()
        with closing(_connect()) as connection:
            connection.execute("DELETE FROM conversation_messages")
            for conversation_id, messages in conversations.items():
                if not isinstance(messages, list):
                    continue
                for message in messages:
                    if not isinstance(message, dict):
                        continue
                    role = str(message.get("role") or "").strip()
                    content = str(message.get("content") or "").strip()
                    created_at = _parse_timestamp(message.get("created_at"))
                    if role not in {"user", "assistant"} or not content or created_at is None:
                        continue
                    connection.execute(
                        """
                        INSERT INTO conversation_messages(
                            conversation_id, role, content, created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (str(conversation_id), role, content, created_at),
                    )
            _cleanup_conversations(connection)
            connection.commit()


def insert_semantic_cache_entry(
    *,
    entry_id: str,
    question: str,
    answer: str,
    citations: list[dict[str, Any]],
    selected_forms: list[str],
    active_index: str,
    model_name: str,
    embed_model_name: str,
) -> None:
    with STATE_DB_LOCK:
        init_state_db()
        now = datetime.now().isoformat(timespec="seconds")
        with closing(_connect()) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO semantic_cache_entries(
                    id, question, normalized_question, answer,
                    citations_json, selected_forms_json,
                    active_index, model_name, embed_model_name, created_at,
                    hit_count, last_hit_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                """,
                (
                    entry_id,
                    question,
                    normalize_semantic_question(question),
                    answer,
                    json.dumps(citations, ensure_ascii=False),
                    json.dumps(selected_forms, ensure_ascii=False),
                    active_index,
                    model_name,
                    embed_model_name,
                    now,
                ),
            )
            connection.commit()


def _semantic_entry_from_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        citations = json.loads(str(row["citations_json"]))
    except json.JSONDecodeError:
        citations = []
    try:
        selected_forms = json.loads(str(row["selected_forms_json"]))
    except json.JSONDecodeError:
        selected_forms = []
    return {
        "id": str(row["id"]),
        "question": str(row["question"]),
        "answer": str(row["answer"]),
        "citations": citations if isinstance(citations, list) else [],
        "selected_forms": selected_forms if isinstance(selected_forms, list) else [],
        "active_index": str(row["active_index"]),
        "model_name": str(row["model_name"]),
        "embed_model_name": str(row["embed_model_name"]),
        "created_at": str(row["created_at"]),
        "hit_count": int(row["hit_count"]),
        "last_hit_at": str(row["last_hit_at"]) if row["last_hit_at"] else None,
    }


def get_semantic_cache_entry(entry_id: str) -> dict[str, Any] | None:
    with STATE_DB_LOCK:
        init_state_db()
        with closing(_connect()) as connection:
            row = connection.execute(
                "SELECT * FROM semantic_cache_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
    if row is None:
        return None
    return _semantic_entry_from_row(row)


def get_semantic_cache_entry_by_question(
    question: str,
    *,
    active_index: str,
    model_name: str,
    embed_model_name: str,
) -> dict[str, Any] | None:
    with STATE_DB_LOCK:
        init_state_db()
        normalized_question = normalize_semantic_question(question)
        with closing(_connect()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM semantic_cache_entries
                WHERE normalized_question = ?
                  AND active_index = ?
                  AND model_name = ?
                  AND embed_model_name = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    normalized_question,
                    active_index,
                    model_name,
                    embed_model_name,
                ),
            ).fetchone()
    return _semantic_entry_from_row(row) if row is not None else None


def mark_semantic_cache_hit(entry_id: str) -> None:
    with STATE_DB_LOCK:
        init_state_db()
        now = datetime.now().isoformat(timespec="seconds")
        with closing(_connect()) as connection:
            connection.execute(
                """
                UPDATE semantic_cache_entries
                SET hit_count = hit_count + 1, last_hit_at = ?
                WHERE id = ?
                """,
                (now, entry_id),
            )
            connection.commit()


def clear_semantic_cache() -> int:
    # Hapus semua entri semantic cache; dipakai saat vector index dibangun ulang.
    with STATE_DB_LOCK:
        init_state_db()
        with closing(_connect()) as connection:
            cursor = connection.execute("DELETE FROM semantic_cache_entries")
            connection.commit()
            return cursor.rowcount


def state_counts() -> dict[str, int]:
    with STATE_DB_LOCK:
        init_state_db()
        with closing(_connect()) as connection:
            conversation_rows = int(
                connection.execute("SELECT COUNT(*) AS count FROM conversation_messages").fetchone()["count"]
            )
            semantic_rows = int(
                connection.execute("SELECT COUNT(*) AS count FROM semantic_cache_entries").fetchone()["count"]
            )
            activity_rows = int(
                connection.execute("SELECT COUNT(*) AS count FROM activity_logs").fetchone()["count"]
            )
    return {
        "conversation_messages": conversation_rows,
        "semantic_cache_entries": semantic_rows,
        "activity_logs": activity_rows,
    }
