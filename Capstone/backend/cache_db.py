from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
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

SCHEMA_VERSION = "1"
MIGRATION_KEY = "conversations_json_migrated"


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
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


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
    with closing(_connect(db_path)) as connection:
        _init_schema(connection)
        if _get_meta(connection, MIGRATION_KEY) != "1":
            _migrate_legacy_conversations(connection, legacy_conversations_path)
            _set_meta(connection, MIGRATION_KEY, "1")
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


def get_conversation_context(conversation_id: str) -> str:
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


def load_conversations() -> dict[str, list[dict[str, object]]]:
    init_state_db()
    conversations: dict[str, list[dict[str, object]]] = {}
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
    init_state_db()
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_connect()) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO semantic_cache_entries(
                id, question, answer, citations_json, selected_forms_json,
                active_index, model_name, embed_model_name, created_at,
                hit_count, last_hit_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            """,
            (
                entry_id,
                question,
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


def get_semantic_cache_entry(entry_id: str) -> dict[str, Any] | None:
    init_state_db()
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM semantic_cache_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
    if row is None:
        return None
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


def mark_semantic_cache_hit(entry_id: str) -> None:
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


def state_counts() -> dict[str, int]:
    init_state_db()
    with closing(_connect()) as connection:
        conversation_rows = int(
            connection.execute("SELECT COUNT(*) AS count FROM conversation_messages").fetchone()["count"]
        )
        semantic_rows = int(
            connection.execute("SELECT COUNT(*) AS count FROM semantic_cache_entries").fetchone()["count"]
        )
    return {
        "conversation_messages": conversation_rows,
        "semantic_cache_entries": semantic_rows,
    }
