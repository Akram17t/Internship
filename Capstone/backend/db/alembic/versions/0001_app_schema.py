"""create app schema (8 operational tables)

Revision ID: 0001_app_schema
Revises:
Create Date: 2026-07-31

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_app_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")

    op.create_table(
        "app_state_meta",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        schema="app",
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=False),
        schema="app",
    )
    op.create_index("idx_users_email", "users", ["email"], schema="app")

    op.create_table(
        "admin_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("password", sa.String(), nullable=False, server_default=""),
        sa.Column("name", sa.String(), nullable=False, server_default="Admin"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="app",
    )
    op.create_index("idx_admin_accounts_email", "admin_accounts", ["email"], schema="app")

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="app",
    )
    op.create_index(
        "idx_conversations_user", "conversations", ["user_id", "updated_at"], schema="app"
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("app.conversations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_conversation_messages_role"),
        schema="app",
    )
    op.create_index(
        "idx_conversation_messages_lookup",
        "conversation_messages",
        ["conversation_id", "created_at", "id"],
        schema="app",
    )
    op.create_index(
        "idx_conversation_messages_created",
        "conversation_messages",
        ["created_at"],
        schema="app",
    )

    op.create_table(
        "semantic_cache_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("normalized_question", sa.Text(), nullable=False, server_default=""),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "selected_forms_json", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("active_index", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("embed_model_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.create_index(
        "idx_semantic_cache_exact",
        "semantic_cache_entries",
        ["normalized_question", "active_index", "model_name", "embed_model_name"],
        schema="app",
    )

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("details_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('chat', 'document')", name="ck_activity_logs_event_type"
        ),
        sa.CheckConstraint("status IN ('success', 'error')", name="ck_activity_logs_status"),
        schema="app",
    )
    op.create_index(
        "idx_activity_logs_lookup",
        "activity_logs",
        ["event_type", sa.text("created_at DESC"), sa.text("id DESC")],
        schema="app",
    )
    op.create_index(
        "idx_activity_logs_created",
        "activity_logs",
        [sa.text("created_at DESC"), sa.text("id DESC")],
        schema="app",
    )

    op.create_table(
        "faq_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(), nullable=False, server_default=""),
        sa.Column("suggested_query", sa.Text(), nullable=False, server_default=""),
        sa.Column("citations_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("image_url", sa.String(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="app",
    )
    op.create_index(
        "idx_faq_items_order",
        "faq_items",
        ["sort_order", "created_at", "id"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("faq_items", schema="app")
    op.drop_table("activity_logs", schema="app")
    op.drop_table("semantic_cache_entries", schema="app")
    op.drop_table("conversation_messages", schema="app")
    op.drop_table("conversations", schema="app")
    op.drop_table("admin_accounts", schema="app")
    op.drop_table("users", schema="app")
    op.drop_table("app_state_meta", schema="app")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
