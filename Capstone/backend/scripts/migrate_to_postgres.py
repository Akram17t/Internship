from __future__ import annotations

"""Simplified SQLite -> PostgreSQL migrator.

Reduced-scope version of the full design's MigrationRunner: reads all 8
SQLite tables via a read-only snapshot, transforms basic types (bool,
timestamp, JSON), and upserts them into the PostgreSQL `app` schema by
primary key (idempotent re-run). No staging tables, no COPY, no formal
reconciliation report/exception tables - just a row-count summary printed
to stdout.

Usage (from repo root, with DATABASE_BACKEND=postgres configured and Alembic
migrations already applied):

    python -m backend.scripts.migrate_to_postgres [--sqlite-path PATH] [--dry-run]

--dry-run reads and reports counts without writing anything to PostgreSQL.
"""

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.cache_db import get_state_db_path
from backend.db.engine import get_session
from backend.db.models import (
    ActivityLog,
    AdminAccount,
    AppStateMeta,
    Conversation,
    ConversationMessage,
    FaqItem,
    SemanticCacheEntry,
    User,
)

TABLES_IN_ORDER = [
    "app_state_meta",
    "users",
    "admin_accounts",
    "conversations",
    "conversation_messages",
    "semantic_cache_entries",
    "activity_logs",
    "faq_items",
]


def _snapshot_sqlite(source_path: Path) -> Path:
    # Verified read-only snapshot: copy via sqlite3's backup API (consistent
    # even if the source is being written concurrently), then reopen the copy
    # read-only for extraction. Never opens the original file for writing.
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite source database not found: {source_path}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="hr_agent_migration_"))
    snapshot_path = tmp_dir / "app_state_snapshot.db"
    with closing(sqlite3.connect(source_path)) as source_conn:
        with closing(sqlite3.connect(snapshot_path)) as dest_conn:
            source_conn.backup(dest_conn)

    integrity_conn = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
    try:
        result = integrity_conn.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError(f"SQLite snapshot failed integrity check: {result}")
    finally:
        integrity_conn.close()

    return snapshot_path


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_json(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def migrate(sqlite_path: Path, *, dry_run: bool = False) -> dict[str, dict[str, int]]:
    snapshot_path = _snapshot_sqlite(sqlite_path)
    summary: dict[str, dict[str, int]] = {name: {"read": 0, "loaded": 0} for name in TABLES_IN_ORDER}

    read_only_conn = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
    read_only_conn.row_factory = sqlite3.Row
    try:
        session = None if dry_run else get_session()
        try:
            summary["app_state_meta"]["read"] = _migrate_app_state_meta(
                read_only_conn, session
            )
            summary["users"]["read"] = _migrate_users(read_only_conn, session)
            summary["admin_accounts"]["read"] = _migrate_admin_accounts(read_only_conn, session)
            summary["conversations"]["read"] = _migrate_conversations(read_only_conn, session)
            summary["conversation_messages"]["read"] = _migrate_conversation_messages(
                read_only_conn, session
            )
            summary["semantic_cache_entries"]["read"] = _migrate_semantic_cache(
                read_only_conn, session
            )
            summary["activity_logs"]["read"] = _migrate_activity_logs(read_only_conn, session)
            summary["faq_items"]["read"] = _migrate_faq_items(read_only_conn, session)

            for table_name in TABLES_IN_ORDER:
                summary[table_name]["loaded"] = (
                    0 if dry_run else summary[table_name]["read"]
                )

            if session is not None:
                session.commit()
        finally:
            if session is not None:
                session.close()
    finally:
        read_only_conn.close()
        shutil.rmtree(snapshot_path.parent, ignore_errors=True)

    return summary


def _migrate_app_state_meta(conn: sqlite3.Connection, session) -> int:
    rows = conn.execute("SELECT key, value FROM app_state_meta").fetchall()
    if session is not None:
        for row in rows:
            # Never copy the admin session secret across environments; it is
            # regenerated locally by init_state_db() on first use instead.
            if str(row["key"]) == "admin_session_secret":
                continue
            stmt = (
                pg_insert(AppStateMeta)
                .values(key=row["key"], value=row["value"])
                .on_conflict_do_update(index_elements=["key"], set_={"value": row["value"]})
            )
            session.execute(stmt)
    return len(rows)


def _migrate_users(conn: sqlite3.Connection, session) -> int:
    rows = conn.execute("SELECT * FROM users").fetchall()
    if session is not None:
        for row in rows:
            stmt = (
                pg_insert(User)
                .values(
                    id=row["id"],
                    email=row["email"],
                    name=row["name"] or "",
                    is_admin=bool(row["is_admin"]),
                    created_at=_parse_ts(row["created_at"]) or datetime.now(timezone.utc),
                    last_login_at=_parse_ts(row["last_login_at"]) or datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "email": row["email"],
                        "name": row["name"] or "",
                        "is_admin": bool(row["is_admin"]),
                    },
                )
            )
            session.execute(stmt)
        _sync_sequence(session, "app.users", "id")
    return len(rows)


def _migrate_admin_accounts(conn: sqlite3.Connection, session) -> int:
    rows = conn.execute("SELECT * FROM admin_accounts").fetchall()
    if session is not None:
        for row in rows:
            stmt = (
                pg_insert(AdminAccount)
                .values(
                    id=row["id"],
                    email=row["email"],
                    password=row["password"] or "",
                    name=row["name"] or "Admin",
                    created_at=_parse_ts(row["created_at"]) or datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={"email": row["email"], "name": row["name"] or "Admin"},
                )
            )
            session.execute(stmt)
        _sync_sequence(session, "app.admin_accounts", "id")
    return len(rows)


def _migrate_conversations(conn: sqlite3.Connection, session) -> int:
    rows = conn.execute("SELECT * FROM conversations").fetchall()
    if session is not None:
        for row in rows:
            stmt = (
                pg_insert(Conversation)
                .values(
                    id=row["id"],
                    user_id=row["user_id"],
                    title=row["title"] or "",
                    created_at=_parse_ts(row["created_at"]) or datetime.now(timezone.utc),
                    updated_at=_parse_ts(row["updated_at"]) or datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={"title": row["title"] or "", "updated_at": _parse_ts(row["updated_at"])},
                )
            )
            session.execute(stmt)
    return len(rows)


def _migrate_conversation_messages(conn: sqlite3.Connection, session) -> int:
    rows = conn.execute("SELECT * FROM conversation_messages").fetchall()
    valid_conversation_ids = set()
    if session is not None:
        valid_conversation_ids = {
            row[0] for row in session.execute(Conversation.__table__.select().with_only_columns(Conversation.id))
        }
    if session is not None:
        for row in rows:
            conversation_id = row["conversation_id"]
            # Orphan messages (no matching parent conversation) are kept with
            # a NULL conversation_id instead of being dropped, per the
            # design's orphan-preservation intent, simplified (no separate
            # exception table/report here).
            fk_value = conversation_id if conversation_id in valid_conversation_ids else None
            stmt = (
                pg_insert(ConversationMessage)
                .values(
                    id=row["id"],
                    conversation_id=fk_value,
                    role=row["role"],
                    content=row["content"],
                    created_at=_parse_ts(row["created_at"]) or datetime.now(timezone.utc),
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(stmt)
        _sync_sequence(session, "app.conversation_messages", "id")
    return len(rows)


def _migrate_semantic_cache(conn: sqlite3.Connection, session) -> int:
    rows = conn.execute("SELECT * FROM semantic_cache_entries").fetchall()
    if session is not None:
        for row in rows:
            stmt = (
                pg_insert(SemanticCacheEntry)
                .values(
                    id=row["id"],
                    question=row["question"],
                    normalized_question=row["normalized_question"] or "",
                    answer=row["answer"],
                    citations_json=_parse_json(row["citations_json"], []),
                    selected_forms_json=_parse_json(row["selected_forms_json"], []),
                    active_index=row["active_index"],
                    model_name=row["model_name"],
                    embed_model_name=row["embed_model_name"],
                    created_at=_parse_ts(row["created_at"]) or datetime.now(timezone.utc),
                    hit_count=row["hit_count"] or 0,
                    last_hit_at=_parse_ts(row["last_hit_at"]),
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(stmt)
    return len(rows)


def _migrate_activity_logs(conn: sqlite3.Connection, session) -> int:
    from backend.analytics.interactions import record_canonical_interaction
    from backend.db.models import CanonicalInteraction
    from sqlalchemy import select

    rows = conn.execute("SELECT * FROM activity_logs").fetchall()
    if session is not None:
        existing_log_ids = {
            row[0]
            for row in session.execute(select(ActivityLog.id))
        }
        already_has_interaction = {
            row[0]
            for row in session.execute(select(CanonicalInteraction.activity_log_id))
            if row[0] is not None
        }
        for row in rows:
            details = _parse_json(row["details_json"], {})
            created_at = _parse_ts(row["created_at"]) or datetime.now(timezone.utc)
            is_new_row = row["id"] not in existing_log_ids
            stmt = (
                pg_insert(ActivityLog)
                .values(
                    id=row["id"],
                    event_type=row["event_type"],
                    action=row["action"] or "",
                    status=row["status"],
                    summary=row["summary"] or "",
                    details_json=details,
                    created_at=created_at,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(stmt)
            if (
                is_new_row
                and row["event_type"] == "chat"
                and row["id"] not in already_has_interaction
            ):
                try:
                    record_canonical_interaction(
                        session,
                        activity_log_id=row["id"],
                        status=row["status"],
                        details=details if isinstance(details, dict) else {},
                        created_at=created_at,
                    )
                except Exception:
                    pass
        _sync_sequence(session, "app.activity_logs", "id")
    return len(rows)


def _migrate_faq_items(conn: sqlite3.Connection, session) -> int:
    rows = conn.execute("SELECT * FROM faq_items").fetchall()
    if session is not None:
        for row in rows:
            stmt = (
                pg_insert(FaqItem)
                .values(
                    id=row["id"],
                    question=row["question"],
                    answer=row["answer"],
                    source=row["source"] or "",
                    source_url=row["source_url"] or "",
                    suggested_query=row["suggested_query"] or "",
                    citations_json=_parse_json(row["citations_json"], []),
                    image_url=row["image_url"] or "",
                    sort_order=row["sort_order"] or 0,
                    created_at=_parse_ts(row["created_at"]) or datetime.now(timezone.utc),
                    updated_at=_parse_ts(row["updated_at"]) or datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "question": row["question"],
                        "answer": row["answer"],
                        "sort_order": row["sort_order"] or 0,
                    },
                )
            )
            session.execute(stmt)
    return len(rows)


def _sync_sequence(session, table: str, column: str) -> None:
    # After loading explicit IDs, bump the identity sequence above the max
    # migrated ID so the next INSERT without an explicit ID doesn't collide.
    from sqlalchemy import text

    session.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
            f"COALESCE((SELECT MAX({column}) FROM {table}), 1), true)"
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=None,
        help="Path to the source SQLite database (defaults to APP_STATE_DB from env).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and report counts only; do not write to PostgreSQL.",
    )
    args = parser.parse_args()

    source_path = args.sqlite_path or get_state_db_path()
    print(f"Source SQLite database: {source_path}")
    print(f"Mode: {'DRY RUN (no writes)' if args.dry_run else 'LIVE (writing to PostgreSQL)'}")

    summary = migrate(source_path, dry_run=args.dry_run)

    print("\nTable                       Read      Loaded")
    print("-" * 46)
    total_read = 0
    total_loaded = 0
    for table_name in TABLES_IN_ORDER:
        counts = summary[table_name]
        print(f"{table_name:<28}{counts['read']:>6}{counts['loaded']:>12}")
        total_read += counts["read"]
        total_loaded += counts["loaded"]
    print("-" * 46)
    print(f"{'TOTAL':<28}{total_read:>6}{total_loaded:>12}")

    if args.dry_run:
        print("\nDry run complete. No data was written to PostgreSQL.")
    else:
        print("\nMigration complete.")


if __name__ == "__main__":
    main()
